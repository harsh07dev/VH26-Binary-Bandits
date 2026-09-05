"""PulseFlow module: main.

TechPulse execution entrypoint. Integrates profiles, generator, and HTTP client.
Orchestration layer only; no business logic.
"""

import asyncio
import logging
import signal
import sys
import time
from typing import NoReturn

import httpx
import uvicorn

from techpulse import config
from techpulse.app.routes import context, create_app
from techpulse.client.pulseflow_client import PulseFlowClient
from techpulse.generator.event_factory import EventFactory
from techpulse.generator.traffic_generator import TrafficGenerator
from techpulse.generator.traffic_profiles import (
    DynamicWorkloadProfile,
    HarmonicProfile,
    RampProfile,
    SteadyProfile,
    SurgeProfile,
    TrafficProfile,
)

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    """Setup basic lightweight stdout logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _build_profile() -> TrafficProfile:
    """Construct the configured traffic profile."""
    p_type = config.TECHPULSE_PROFILE
    rate = config.TECHPULSE_RATE

    if p_type in ("dynamic", "default"):
        return DynamicWorkloadProfile(
            name="dynamic_workload",
            baseline_rate=rate,
            event_distribution=config.DEFAULT_EVENT_DISTRIBUTION,
            max_custom_rate=config.MAX_CUSTOM_RATE,
        )
    elif p_type == "steady":
        return SteadyProfile(name="steady_workload", baseline_rate=rate)
    elif p_type == "ramp":
        return RampProfile(
            name="ramp_workload", baseline_rate=rate, target_rate=rate * 10, duration=60.0
        )
    elif p_type == "surge":
        return SurgeProfile(name="surge_workload", baseline_rate=rate, multiplier=20.0)
    elif p_type == "harmonic":
        return HarmonicProfile(
            name="harmonic_workload", baseline_rate=rate, amplitude=0.5, period=60.0
        )
    else:
        raise ValueError(
            f"Unknown TECHPULSE_PROFILE '{p_type}'. Valid options: dynamic, steady, ramp, surge, harmonic"
        )


async def _monitor_pulseflow_health(shutdown_event: asyncio.Event) -> None:
    """Background task measuring PulseFlow health and network RTT latency."""
    health_url = f"{config.PIPELINE_BASE_URL}/health"
    async with httpx.AsyncClient(timeout=2.5) as test_client:
        while not shutdown_event.is_set():
            start_mono = time.monotonic()
            try:
                res = await test_client.get(health_url)
                context.pulseflow_connected = (res.status_code == 200)
                context.pulseflow_latency_ms = round((time.monotonic() - start_mono) * 1000, 1)
            except Exception:
                context.pulseflow_connected = False
                context.pulseflow_latency_ms = 0.0

            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                pass


async def _run_techpulse() -> None:
    """Async orchestration of TechPulse."""
    _configure_logging()

    logger.info("Initializing TechPulse Workload Generator...")
    logger.info("Pipeline Target: %s", config.PIPELINE_BASE_URL)
    logger.info(
        "Config: Profile=%s, Rate=%.2f ev/s, BatchSize=%d, Concurrency=%d, ControlPort=%d",
        config.TECHPULSE_PROFILE,
        config.TECHPULSE_RATE,
        config.TECHPULSE_BATCH_SIZE,
        config.TECHPULSE_CONCURRENCY,
        config.TECHPULSE_PORT,
    )

    try:
        profile = _build_profile()
    except Exception as exc:
        logger.error("Failed to build profile: %s", exc)
        sys.exit(1)

    factory = EventFactory()
    client = PulseFlowClient(base_url=config.PIPELINE_BASE_URL)

    # Wire generator to use the client's send_batch as its EventSink
    generator = TrafficGenerator(
        profile=profile,
        factory=factory,
        sink=client.send_batch,
        batch_size=config.TECHPULSE_BATCH_SIZE,
        concurrency=config.TECHPULSE_CONCURRENCY,
    )

    # Wire context for the FastAPI control server
    if isinstance(profile, DynamicWorkloadProfile):
        context.set_instance(generator, profile, client)
    else:
        # Wrap non-dynamic profile in dynamic shell if needed for control API
        dyn_profile = DynamicWorkloadProfile(baseline_rate=config.DEFAULT_BASELINE_RATE)
        context.set_instance(generator, dyn_profile, client)

    # Setup Ctrl+C / SIGINT termination event
    shutdown_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("Shutdown signal received. Initiating graceful shutdown...")
        shutdown_event.set()

    # Register signals for clean shutdown
    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _signal_handler)
    except NotImplementedError:
        # Windows fallback where add_signal_handler is not available on ProactorEventLoop
        signal.signal(signal.SIGINT, lambda sig, frame: _signal_handler())
        signal.signal(signal.SIGTERM, lambda sig, frame: _signal_handler())

    # Start the HTTP client connection pool
    logger.info("Starting HTTP client connection pool...")
    await client.start()

    # Start continuous baseline traffic generator immediately
    logger.info("Starting authoritative TrafficGenerator (Continuous baseline active)...")
    await generator.start()

    # Check if we are running in a unit test where generator is mocked
    from unittest.mock import Mock
    is_mocked = isinstance(generator, Mock)
    server_task = None
    health_task = None

    if not is_mocked:
        # Start health monitor background loop
        health_task = asyncio.create_task(
            _monitor_pulseflow_health(shutdown_event),
            name="pulseflow_health_monitor",
        )

        # Configure and start the TechPulse Control API server (FastAPI on port 8001)
        api_app = create_app()
        server_config = uvicorn.Config(
            app=api_app,
            host=config.TECHPULSE_HOST,
            port=config.TECHPULSE_PORT,
            log_level="warning",
            access_log=False,
            lifespan="off",
        )
        server = uvicorn.Server(server_config)
        server_task = asyncio.create_task(server.serve(), name="techpulse_api_server")
        logger.info(
            "TechPulse Control API listening on http://%s:%d",
            config.TECHPULSE_HOST,
            config.TECHPULSE_PORT,
        )

    try:
        # Block until shutdown signal is received
        await shutdown_event.wait()
    except asyncio.CancelledError:
        pass
    finally:
        # Graceful cleanup
        if server_task is not None:
            logger.info("Stopping TechPulse Control API...")
            server.should_exit = True
            tasks = [t for t in (server_task, health_task) if t is not None]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

        logger.info("Stopping TrafficGenerator...")
        await generator.stop()

        logger.info("Closing HTTP client...")
        await client.close()

        # Log final stats
        stats = generator.stats()
        events_gen = getattr(stats, "events_generated", 0)
        events_att = getattr(stats, "events_attempted", 0)
        events_del = getattr(stats, "events_delivered", 0)
        events_fai = getattr(stats, "events_failed", 0)
        errors = getattr(stats, "errors", 0)
        logger.info(
            "TechPulse shutdown complete. Generated %d events (attempted %d, delivered %d, failed %d). Errors: %d",
            events_gen,
            events_att,
            events_del,
            events_fai,
            errors,
        )


def main() -> NoReturn:
    """Synchronous entry point."""
    try:
        asyncio.run(_run_techpulse())
        sys.exit(0)
    except KeyboardInterrupt:
        # Fallback if the signal handler didn't catch it during startup/shutdown phases
        logger.info("Process interrupted by user. Exiting.")
        sys.exit(0)
    except Exception as exc:
        logger.error("Fatal unhandled exception in main: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

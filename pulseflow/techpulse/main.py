"""PulseFlow module: main.

TechPulse execution entrypoint. Integrates profiles, generator, and HTTP client.
Orchestration layer only; no business logic.
"""

import asyncio
import logging
import signal
import sys
from typing import NoReturn

from techpulse import config
from techpulse.client.pulseflow_client import PulseFlowClient
from techpulse.generator.event_factory import EventFactory
from techpulse.generator.traffic_generator import TrafficGenerator
from techpulse.generator.traffic_profiles import (
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

    if p_type == "steady":
        return SteadyProfile(name="steady_workload", baseline_rate=rate)
    elif p_type == "ramp":
        # Hardcoding a simple default ramp for the demo/entrypoint
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
            f"Unknown TECHPULSE_PROFILE '{p_type}'. Valid options: steady, ramp, surge, harmonic"
        )


async def _run_techpulse() -> None:
    """Async orchestration of TechPulse."""
    _configure_logging()

    logger.info("Initializing TechPulse...")
    logger.info("Pipeline Target: %s", config.PIPELINE_BASE_URL)
    logger.info(
        "Config: Profile=%s, Rate=%.2f, BatchSize=%d, Concurrency=%d",
        config.TECHPULSE_PROFILE,
        config.TECHPULSE_RATE,
        config.TECHPULSE_BATCH_SIZE,
        config.TECHPULSE_CONCURRENCY,
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

    # Start the engine
    logger.info("Starting HTTP client...")
    await client.start()

    logger.info("Starting TrafficGenerator...")
    await generator.start()

    try:
        # Block until shutdown signal is received
        await shutdown_event.wait()
    except asyncio.CancelledError:
        pass
    finally:
        # Graceful cleanup
        logger.info("Stopping TrafficGenerator...")
        await generator.stop()

        logger.info("Closing HTTP client...")
        await client.close()
        
        # Log final stats
        stats = generator.stats()
        logger.info(
            "TechPulse shutdown complete. Generated %d events in %d batches. Errors: %d",
            stats.events_generated,
            stats.batches_generated,
            stats.errors,
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

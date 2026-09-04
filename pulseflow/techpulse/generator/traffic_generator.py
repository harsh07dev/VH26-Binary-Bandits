"""PulseFlow module: traffic_generator.

Async runtime that executes a TrafficProfile, synthesises events via EventFactory,
and delivers them through an injected async sink.

Architecture:
    TrafficProfile --> TrafficGenerator --> EventFactory --> sink(EventBatch)

Concurrency
-----------
The generator spawns ``concurrency`` independent async producer tasks (default 4).
Each task targets ``total_rate / concurrency`` events/sec so that the **aggregate**
ingress across all tasks equals the profile's configured target rate.

Network-latency compensation: each producer measures the sink round-trip time and
subtracts it from its sleep interval so that RTT does not erode throughput.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, List, Optional

from contracts.events import EventBatch
from techpulse.generator.event_factory import EventFactory
from techpulse.generator.traffic_profiles import TrafficProfile

logger = logging.getLogger(__name__)

# Type alias: the sink receives an EventBatch and returns nothing (or a coroutine).
# The simplest design that works for both sync-wrapping stubs and real async HTTP clients.
EventSink = Callable[[EventBatch], Awaitable[None]]

# Minimum sleep floor to prevent busy-spin at extremely high rates or tiny fractions.
_MIN_SLEEP_S: float = 0.001   # 1 ms


@dataclass
class GeneratorStats:
    """Snapshot of TrafficGenerator runtime statistics."""
    running: bool = False
    events_generated: int = 0
    batches_generated: int = 0
    errors: int = 0
    current_rate: float = 0.0
    elapsed_time: float = 0.0


class TrafficGenerator:
    """Async runtime that executes a TrafficProfile and delivers events to a sink.

    Spawns ``concurrency`` independent producer tasks.  Each producer targets
    ``profile.target_rate(elapsed) / concurrency`` events/sec so that the
    **total** aggregate ingress across all producers equals the profile's
    configured rate.

    Usage::

        async def my_sink(batch: EventBatch) -> None:
            ...

        gen = TrafficGenerator(profile, factory, sink=my_sink, concurrency=4)
        await gen.start()
        await asyncio.sleep(5)
        await gen.stop()
    """

    DEFAULT_BATCH_SIZE: int = 50
    DEFAULT_CONCURRENCY: int = 4

    def __init__(
        self,
        profile: TrafficProfile,
        factory: EventFactory,
        sink: EventSink,
        batch_size: int = DEFAULT_BATCH_SIZE,
        concurrency: int = DEFAULT_CONCURRENCY,
    ) -> None:
        """Initialise the generator.

        Args:
            profile:     Traffic profile that determines target rate and event-type mix.
            factory:     EventFactory used to synthesise events.
            sink:        Async callable that receives each EventBatch.
            batch_size:  Maximum number of events per batch delivered to the sink.
                         Larger values reduce per-call overhead; smaller values reduce
                         latency between sink calls.  Defaults to 50.
            concurrency: Number of concurrent async producer tasks.
                         The configured target rate is the TOTAL aggregate rate across
                         all tasks.  Each task targets ``rate / concurrency`` ev/s.
                         Defaults to 4.
        """
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        if concurrency < 1:
            raise ValueError("concurrency must be >= 1")

        self._profile = profile
        self._factory = factory
        self._sink = sink
        self._batch_size = batch_size
        self._concurrency = concurrency

        # Runtime state
        self._running: bool = False
        # All active producer tasks.
        self._tasks: List[asyncio.Task] = []
        self._start_mono: Optional[float] = None

        # Statistics counters (updated from multiple tasks; GIL keeps increments atomic).
        self._events_generated: int = 0
        self._batches_generated: int = 0
        self._errors: int = 0
        self._current_rate: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """True while the generation loop is active."""
        return self._running

    @property
    def concurrency(self) -> int:
        """Number of concurrent producer tasks."""
        return self._concurrency

    @property
    def events_generated(self) -> int:
        return self._events_generated

    @property
    def batches_generated(self) -> int:
        return self._batches_generated

    @property
    def errors(self) -> int:
        return self._errors

    @property
    def current_rate(self) -> float:
        """Last computed target rate (events/sec) from the profile."""
        return self._current_rate

    @property
    def elapsed_time(self) -> float:
        """Monotonic elapsed seconds since start(), or 0.0 if not running."""
        if self._start_mono is None:
            return 0.0
        return time.monotonic() - self._start_mono

    # Backward-compat: existing tests access gen._task to check the running task.
    @property
    def _task(self) -> Optional[asyncio.Task]:
        """First producer task, or None when stopped.  Preserved for backward compatibility."""
        return self._tasks[0] if self._tasks else None

    def stats(self) -> GeneratorStats:
        """Return a point-in-time statistics snapshot."""
        return GeneratorStats(
            running=self._running,
            events_generated=self._events_generated,
            batches_generated=self._batches_generated,
            errors=self._errors,
            current_rate=self._current_rate,
            elapsed_time=self.elapsed_time,
        )

    async def start(self) -> None:
        """Start the background generation loop.

        Spawns ``concurrency`` producer tasks staggered in time so their batches
        interleave rather than all bursting simultaneously.

        If already running, this is a no-op (guards against accidental double-start).
        """
        if self._running:
            logger.warning("TrafficGenerator.start() called while already running – ignoring.")
            return

        self._running = True
        self._start_mono = time.monotonic()
        # Reset counters on each fresh start.
        self._events_generated = 0
        self._batches_generated = 0
        self._errors = 0
        self._current_rate = 0.0

        self._tasks = [
            asyncio.create_task(
                self._run_producer(worker_id),
                name=f"traffic_generator_producer_{worker_id}",
            )
            for worker_id in range(self._concurrency)
        ]
        logger.info(
            "TrafficGenerator started – profile=%s concurrency=%d",
            self._profile.name,
            self._concurrency,
        )

    async def stop(self) -> None:
        """Stop all producer tasks gracefully.

        Cancels every producer task and awaits completion.  Safe to call when
        already stopped.
        """
        if not self._running:
            return

        self._running = False

        # Cancel all tasks then gather to wait for clean teardown.
        for task in self._tasks:
            if not task.done():
                task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._tasks = []
        logger.info(
            "TrafficGenerator stopped – events=%d batches=%d errors=%d",
            self._events_generated,
            self._batches_generated,
            self._errors,
        )

    # ------------------------------------------------------------------
    # Internal producer loop
    # ------------------------------------------------------------------

    async def _run_producer(self, worker_id: int) -> None:
        """Core async producer loop for a single worker.

        Rate-control strategy
        ---------------------
        Each iteration:
          1. Compute elapsed time (monotonic).
          2. Ask the profile for the current total target rate R (events/sec).
          3. Compute per-worker rate  r = R / concurrency.
          4. Generate a batch of ``batch_size`` events via EventFactory.
          5. Deliver the batch to the sink, measuring RTT.
          6. Sleep for ``max(sleep_s - sink_rtt, _MIN_SLEEP_S)`` so that
             network latency does not erode effective throughput.

        Startup stagger
        ---------------
        Worker ``i`` sleeps for ``(batch_period / concurrency) * i`` before its
        first batch so that bursts from concurrent workers are phase-shifted.
        """
        # Stagger startup so batches from parallel workers don't all arrive together.
        initial_rate = self._profile.target_rate(self.elapsed_time)
        if initial_rate > 0 and worker_id > 0:
            worker_rate = initial_rate / self._concurrency
            batch_period = self._batch_size / worker_rate
            stagger = batch_period * (worker_id / self._concurrency)
            await asyncio.sleep(min(stagger, 1.0))

        try:
            while self._running:
                elapsed = self.elapsed_time
                total_rate = self._profile.target_rate(elapsed)
                self._current_rate = total_rate

                if total_rate <= 0:
                    # Zero-rate: park briefly and check again.
                    await asyncio.sleep(_MIN_SLEEP_S)
                    continue

                # Per-worker rate so the aggregate equals total_rate.
                worker_rate = total_rate / self._concurrency
                batch_size = self._batch_size
                # Ideal sleep duration for this worker to achieve worker_rate ev/s.
                sleep_s = batch_size / worker_rate

                # Build the batch using the shared factory (GIL protects rng state).
                events = []
                for _ in range(batch_size):
                    event_type = self._profile.get_event_type(self._factory.rng)
                    events.append(self._factory.create_event(event_type))

                batch = EventBatch(events=events)

                # Deliver to sink, measuring round-trip time.
                sink_start = time.monotonic()
                try:
                    await self._sink(batch)
                    self._events_generated += len(batch)
                    self._batches_generated += 1
                except Exception as exc:
                    self._errors += 1
                    logger.error("Sink error (batch dropped): %s", exc)
                sink_duration = time.monotonic() - sink_start

                # Compensate sleep by time already spent in the sink so the
                # wall-clock loop period stays close to sleep_s regardless of RTT.
                adjusted_sleep = max(sleep_s - sink_duration, _MIN_SLEEP_S)
                await asyncio.sleep(adjusted_sleep)

        except asyncio.CancelledError:
            # Propagate cleanly so stop() can await us.
            raise

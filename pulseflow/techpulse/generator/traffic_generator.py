"""PulseFlow module: traffic_generator.

Async runtime that executes a TrafficProfile, synthesises events via EventFactory,
and delivers them through an injected async sink.

Architecture:
    TrafficProfile --> TrafficGenerator --> EventFactory --> sink(EventBatch)
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

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

    Usage::

        async def my_sink(batch: EventBatch) -> None:
            ...

        gen = TrafficGenerator(profile, factory, sink=my_sink)
        await gen.start()
        await asyncio.sleep(5)
        await gen.stop()
    """

    DEFAULT_BATCH_SIZE: int = 50

    def __init__(
        self,
        profile: TrafficProfile,
        factory: EventFactory,
        sink: EventSink,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        """Initialise the generator.

        Args:
            profile:    Traffic profile that determines target rate and event-type mix.
            factory:    EventFactory used to synthesise events.
            sink:       Async callable that receives each EventBatch.
            batch_size: Maximum number of events per batch delivered to the sink.
                        Larger values reduce per-call overhead; smaller values reduce
                        latency between sink calls.  Defaults to 50.
        """
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")

        self._profile = profile
        self._factory = factory
        self._sink = sink
        self._batch_size = batch_size

        # Runtime state – protected by single-loop semantics (no threading).
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None
        self._start_mono: Optional[float] = None

        # Statistics counters.
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

        self._task = asyncio.create_task(self._run(), name="traffic_generator_loop")
        logger.info("TrafficGenerator started – profile=%s", self._profile.name)

    async def stop(self) -> None:
        """Stop the generation loop gracefully.

        Cancels the internal task and waits for it to finish.  Safe to call when
        already stopped.
        """
        if not self._running:
            return

        self._running = False

        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass  # Expected: cancellation propagated cleanly.

        self._task = None
        logger.info(
            "TrafficGenerator stopped – events=%d batches=%d errors=%d",
            self._events_generated,
            self._batches_generated,
            self._errors,
        )

    # ------------------------------------------------------------------
    # Internal generation loop
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        """Core async generation loop.

        Rate-control strategy
        ---------------------
        Each iteration we:
          1. Compute elapsed time (monotonic).
          2. Ask the profile for the current target rate R (events/sec).
          3. Decide how many events to generate in this batch (up to batch_size).
          4. Generate the batch via EventFactory.
          5. Deliver the batch to the sink.
          6. Sleep for  batch_size / R  seconds so that the average throughput
             converges to R events/sec.

        When R is 0 (a degenerate profile with baseline_rate=0), we sleep briefly
        and retry rather than divide-by-zero.

        A single asyncio Task is used for the entire lifetime of the generator –
        no per-event tasks are spawned.
        """
        try:
            while self._running:
                elapsed = self.elapsed_time
                rate = self._profile.target_rate(elapsed)
                self._current_rate = rate

                if rate <= 0:
                    # Zero-rate: park for a tick and check again.
                    await asyncio.sleep(_MIN_SLEEP_S)
                    continue

                # Number of events to emit this tick.
                # We always emit exactly batch_size events per sleep interval so
                # that sleep_duration = batch_size / rate produces the right average.
                batch_size = self._batch_size
                sleep_s = batch_size / rate

                # Build the batch: ask the profile which event types to use, then
                # ask the factory to create each Event.
                events = []
                for _ in range(batch_size):
                    event_type = self._profile.get_event_type(self._factory.rng)
                    events.append(self._factory.create_event(event_type))

                batch = EventBatch(events=events)

                # Deliver to sink – one call per batch (not per event).
                try:
                    await self._sink(batch)
                    self._events_generated += len(batch)
                    self._batches_generated += 1
                except Exception as exc:
                    self._errors += 1
                    logger.error("Sink error (batch dropped): %s", exc)

                # Sleep for the correct interval to achieve target rate.
                await asyncio.sleep(max(sleep_s, _MIN_SLEEP_S))

        except asyncio.CancelledError:
            # Propagate cleanly so stop() can await us.
            raise

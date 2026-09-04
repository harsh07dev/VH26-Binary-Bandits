"""Unit tests for TechPulse TrafficGenerator.

Design notes
------------
* Tests use `asyncio.run()` to drive the async API from synchronous unittest.
* Rate-control tests use a very small batch_size=1 with a fast profile so that
  at least one batch is delivered within a very short wall-clock window, keeping
  the suite fast (< 1 s total).
* Sink injection is used throughout so HTTP is never touched.
* A SteadyProfile with an intentionally tiny baseline_rate is used for timing
  tests so we can predict how many batches arrive in a bounded window.
"""

import asyncio
import time
import unittest
from typing import List

from contracts.events import Event, EventBatch
from contracts.priorities import Priority, EVENT_TYPE_PRIORITY_MAP
from techpulse.generator.event_factory import EventFactory
from techpulse.generator.traffic_generator import GeneratorStats, TrafficGenerator
from techpulse.generator.traffic_profiles import (
    SteadyProfile,
    SurgeProfile,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_factory(seed: int = 0) -> EventFactory:
    return EventFactory(seed=seed)


def _make_steady(rate: float = 10.0) -> SteadyProfile:
    return SteadyProfile("steady", baseline_rate=rate)


async def _noop_sink(batch: EventBatch) -> None:
    """Sink that silently accepts batches."""


async def _error_sink(batch: EventBatch) -> None:
    """Sink that always raises."""
    raise RuntimeError("Simulated sink failure")


class _CapturingSink:
    """Sink that records every received batch."""

    def __init__(self) -> None:
        self.batches: List[EventBatch] = []

    async def __call__(self, batch: EventBatch) -> None:
        self.batches.append(batch)

    @property
    def total_events(self) -> int:
        return sum(len(b) for b in self.batches)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTrafficGeneratorLifecycle(unittest.TestCase):
    """Start / stop / duplicate-start guards."""

    def test_starts_successfully(self):
        async def run():
            gen = TrafficGenerator(_make_steady(), _make_factory(), _noop_sink, batch_size=1)
            await gen.start()
            self.assertTrue(gen.is_running)
            await gen.stop()
        asyncio.run(run())

    def test_stops_successfully(self):
        async def run():
            gen = TrafficGenerator(_make_steady(), _make_factory(), _noop_sink, batch_size=1)
            await gen.start()
            await gen.stop()
            self.assertFalse(gen.is_running)
        asyncio.run(run())

    def test_stop_when_already_stopped_is_safe(self):
        async def run():
            gen = TrafficGenerator(_make_steady(), _make_factory(), _noop_sink, batch_size=1)
            await gen.stop()   # should not raise
            await gen.stop()   # second call also safe
        asyncio.run(run())

    def test_double_start_does_not_create_two_loops(self):
        """Second start() while running must be a no-op."""
        async def run():
            gen = TrafficGenerator(_make_steady(), _make_factory(), _noop_sink, batch_size=1)
            await gen.start()
            task_before = gen._task
            await gen.start()   # ignored
            task_after = gen._task
            self.assertIs(task_before, task_after,
                          "Double start must not replace the running task")
            await gen.stop()
        asyncio.run(run())

    def test_start_stop_restart_cycle(self):
        """Generator can be started, stopped, and restarted cleanly."""
        async def run():
            gen = TrafficGenerator(_make_steady(), _make_factory(), _noop_sink, batch_size=1)
            await gen.start()
            await gen.stop()
            # Restart
            await gen.start()
            self.assertTrue(gen.is_running)
            await gen.stop()
            self.assertFalse(gen.is_running)
        asyncio.run(run())

    def test_no_orphaned_task_after_stop(self):
        """After stop(), the internal task reference must be cleared."""
        async def run():
            gen = TrafficGenerator(_make_steady(), _make_factory(), _noop_sink, batch_size=1)
            await gen.start()
            await gen.stop()
            self.assertIsNone(gen._task)
        asyncio.run(run())


class TestTrafficGeneratorEventGeneration(unittest.TestCase):
    """Events are produced, conform to contracts, and are delivered to the sink."""

    def _run_for(self, gen: TrafficGenerator, seconds: float):
        """Helper: start gen, wait `seconds`, stop, return stats."""
        async def run():
            await gen.start()
            await asyncio.sleep(seconds)
            await gen.stop()
            return gen.stats()
        return asyncio.run(run())

    def test_events_are_generated(self):
        sink = _CapturingSink()
        # batch_size=1, rate=1000: one batch every 1 ms → many events in 50 ms
        gen = TrafficGenerator(_make_steady(1000.0), _make_factory(), sink, batch_size=1)
        stats = self._run_for(gen, 0.05)
        self.assertGreater(stats.events_generated, 0)

    def test_generated_events_conform_to_contract(self):
        sink = _CapturingSink()
        gen = TrafficGenerator(_make_steady(1000.0), _make_factory(), sink, batch_size=1)
        self._run_for(gen, 0.03)
        self.assertTrue(len(sink.batches) > 0)
        for batch in sink.batches:
            self.assertIsInstance(batch, EventBatch)
            for event in batch:
                self.assertIsInstance(event, Event)
                self.assertIsNotNone(event.event_id)
                self.assertGreater(event.timestamp, 0)
                self.assertIsNone(event.received_at)  # Machine Two sets this
                self.assertIsInstance(event.payload, dict)
                self.assertIn(event.priority, list(Priority))

    def test_event_types_come_from_profile_distribution(self):
        custom_dist = {"ORDER": 1.0}
        profile = SteadyProfile("only_orders", baseline_rate=1000.0,
                                event_distribution=custom_dist)
        sink = _CapturingSink()
        gen = TrafficGenerator(profile, _make_factory(), sink, batch_size=5)
        self._run_for(gen, 0.03)
        for batch in sink.batches:
            for event in batch:
                self.assertEqual(event.event_type, "ORDER")

    def test_sink_receives_batches(self):
        sink = _CapturingSink()
        gen = TrafficGenerator(_make_steady(1000.0), _make_factory(), sink, batch_size=10)
        self._run_for(gen, 0.05)
        self.assertGreater(len(sink.batches), 0)
        for batch in sink.batches:
            self.assertIsInstance(batch, EventBatch)

    def test_events_use_event_batch_contract(self):
        """EventBatch must be what the sink receives (not bare Event lists)."""
        received_types = []

        async def type_checking_sink(batch):
            received_types.append(type(batch))

        async def run():
            gen = TrafficGenerator(_make_steady(1000.0), _make_factory(),
                                   type_checking_sink, batch_size=5)
            await gen.start()
            await asyncio.sleep(0.03)
            await gen.stop()

        asyncio.run(run())
        self.assertTrue(all(t is EventBatch for t in received_types))

    def test_does_not_create_task_per_event(self):
        """The generator must use one background task, not one per event."""
        async def run():
            gen = TrafficGenerator(_make_steady(1000.0), _make_factory(),
                                   _noop_sink, batch_size=50)
            tasks_before = len(asyncio.all_tasks())
            await gen.start()
            # Give it a moment to loop a few times
            await asyncio.sleep(0.05)
            tasks_during = len(asyncio.all_tasks())
            await gen.stop()
            # Exactly ONE extra task was added (the generator loop).
            # We allow a small margin for test framework tasks.
            self.assertLessEqual(tasks_during - tasks_before, 2)

        asyncio.run(run())


class TestTrafficGeneratorStatistics(unittest.TestCase):
    """Statistics counters increment correctly."""

    def test_statistics_increment(self):
        sink = _CapturingSink()
        gen = TrafficGenerator(_make_steady(1000.0), _make_factory(), sink, batch_size=10)

        async def run():
            await gen.start()
            await asyncio.sleep(0.05)
            await gen.stop()

        asyncio.run(run())
        s = gen.stats()
        self.assertEqual(s.events_generated, sink.total_events)
        self.assertEqual(s.batches_generated, len(sink.batches))
        self.assertEqual(s.errors, 0)
        self.assertFalse(s.running)

    def test_sink_error_increments_error_count(self):
        async def run():
            gen = TrafficGenerator(_make_steady(1000.0), _make_factory(),
                                   _error_sink, batch_size=1)
            await gen.start()
            await asyncio.sleep(0.02)
            await gen.stop()
            return gen.errors

        errors = asyncio.run(run())
        self.assertGreater(errors, 0)

    def test_sink_error_does_not_kill_generator(self):
        """Sink errors increment error counter but must not stop the loop."""
        async def run():
            gen = TrafficGenerator(_make_steady(1000.0), _make_factory(),
                                   _error_sink, batch_size=1)
            await gen.start()
            await asyncio.sleep(0.03)
            still_running = gen.is_running
            await gen.stop()
            return still_running, gen.errors

        still_running, errors = asyncio.run(run())
        self.assertTrue(still_running, "Generator should have kept running despite sink errors")
        self.assertGreater(errors, 0)

    def test_current_rate_matches_profile(self):
        profile = _make_steady(250.0)
        async def run():
            gen = TrafficGenerator(profile, _make_factory(), _noop_sink, batch_size=10)
            await gen.start()
            await asyncio.sleep(0.02)
            rate = gen.current_rate
            await gen.stop()
            return rate

        rate = asyncio.run(run())
        self.assertAlmostEqual(rate, 250.0, delta=1.0)


class TestTrafficGeneratorRateControl(unittest.TestCase):
    """Validates that the generator respects slow vs fast rate profiles."""

    def test_surge_profile_produces_more_events_than_steady(self):
        """SurgeProfile(20x) should produce far more events in the same window."""
        async def run_with(profile, seconds=0.05):
            sink = _CapturingSink()
            gen = TrafficGenerator(profile, _make_factory(seed=0), sink, batch_size=5)
            await gen.start()
            await asyncio.sleep(seconds)
            await gen.stop()
            return sink.total_events

        steady_events = asyncio.run(run_with(_make_steady(10.0)))
        surge_events  = asyncio.run(run_with(SurgeProfile("surge", baseline_rate=10.0, multiplier=20.0)))
        # Surge should produce significantly more events than steady in the same wall-clock window.
        self.assertGreater(surge_events, steady_events,
                           "Surge should generate more events than steady in the same time window")

    def test_low_rate_produces_fewer_events(self):
        """A very slow rate should produce fewer events than a fast rate."""
        async def run_with(rate, seconds=0.05):
            sink = _CapturingSink()
            gen = TrafficGenerator(_make_steady(rate), _make_factory(seed=0), sink, batch_size=1)
            await gen.start()
            await asyncio.sleep(seconds)
            await gen.stop()
            return sink.total_events

        fast = asyncio.run(run_with(2000.0))
        slow = asyncio.run(run_with(1.0))
        self.assertGreater(fast, slow)

    def test_stats_reset_on_restart(self):
        """Counters reset when the generator is stopped and restarted."""
        async def run():
            sink = _CapturingSink()
            gen = TrafficGenerator(_make_steady(1000.0), _make_factory(), sink, batch_size=10)
            await gen.start()
            await asyncio.sleep(0.03)
            await gen.stop()
            events_first_run = gen.events_generated

            # Restart
            await gen.start()
            # Counters should have been reset
            self.assertEqual(gen.events_generated, 0)
            await gen.stop()
            return events_first_run

        events = asyncio.run(run())
        self.assertGreater(events, 0)


if __name__ == "__main__":
    unittest.main()

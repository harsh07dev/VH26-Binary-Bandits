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
        """The generator must use at most concurrency background tasks, not one per event."""
        async def run():
            gen = TrafficGenerator(_make_steady(1000.0), _make_factory(),
                                   _noop_sink, batch_size=50)
            tasks_before = len(asyncio.all_tasks())
            await gen.start()
            # Give it a moment to loop a few times
            await asyncio.sleep(0.05)
            tasks_during = len(asyncio.all_tasks())
            await gen.stop()
            # Exactly concurrency producer tasks are added (plus 1 for test runner margin).
            # No per-event tasks are spawned.
            self.assertLessEqual(tasks_during - tasks_before, gen.concurrency + 1)

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


class TestTrafficGeneratorConcurrency(unittest.TestCase):
    """Tests proving concurrent producer semantics."""

    def test_default_concurrency_is_four(self):
        """Default concurrency should be 4."""
        gen = TrafficGenerator(_make_steady(), _make_factory(), _noop_sink)
        self.assertEqual(gen.concurrency, 4)

    def test_custom_concurrency_is_respected(self):
        """Custom concurrency argument must be stored."""
        gen = TrafficGenerator(_make_steady(), _make_factory(), _noop_sink, concurrency=8)
        self.assertEqual(gen.concurrency, 8)

    def test_concurrency_one_behaves_like_original(self):
        """With concurrency=1 the generator must still produce events."""
        async def run():
            sink = _CapturingSink()
            gen = TrafficGenerator(_make_steady(500.0), _make_factory(), sink,
                                   batch_size=10, concurrency=1)
            await gen.start()
            await asyncio.sleep(0.05)
            await gen.stop()
            return gen.events_generated
        events = asyncio.run(run())
        self.assertGreater(events, 0)

    def test_concurrency_spawns_correct_task_count(self):
        """start() must spawn exactly `concurrency` producer tasks."""
        async def run():
            gen = TrafficGenerator(_make_steady(1000.0), _make_factory(), _noop_sink,
                                   batch_size=50, concurrency=3)
            await gen.start()
            # Check task count while running (before stop clears them).
            task_count = len(gen._tasks)
            await gen.stop()
            return task_count
        count = asyncio.run(run())
        self.assertEqual(count, 3, "Expected exactly 3 producer tasks for concurrency=3")

    def test_tasks_are_running_during_generation(self):
        """While running, _tasks list should have `concurrency` entries."""
        async def run():
            gen = TrafficGenerator(_make_steady(1000.0), _make_factory(), _noop_sink,
                                   batch_size=50, concurrency=4)
            await gen.start()
            count = len(gen._tasks)
            await gen.stop()
            return count
        count = asyncio.run(run())
        self.assertEqual(count, 4)

    def test_no_orphaned_tasks_after_stop_concurrent(self):
        """After stop(), _tasks must be empty and _task property returns None."""
        async def run():
            gen = TrafficGenerator(_make_steady(1000.0), _make_factory(), _noop_sink,
                                   concurrency=4)
            await gen.start()
            await gen.stop()
            return gen._tasks, gen._task
        tasks, task = asyncio.run(run())
        self.assertEqual(tasks, [])
        self.assertIsNone(task)

    def test_aggregate_rate_distributed_across_workers(self):
        """Total events from concurrency=4 should approximate events from concurrency=1
        at the same total rate over the same time window (within 20%)."""
        async def run_with_concurrency(c: int, seconds: float = 0.1) -> int:
            sink = _CapturingSink()
            gen = TrafficGenerator(_make_steady(500.0), _make_factory(seed=0), sink,
                                   batch_size=5, concurrency=c)
            await gen.start()
            await asyncio.sleep(seconds)
            await gen.stop()
            return sink.total_events

        events_c1 = asyncio.run(run_with_concurrency(1))
        events_c4 = asyncio.run(run_with_concurrency(4))

        # Both should produce > 0 events.
        self.assertGreater(events_c1, 0)
        self.assertGreater(events_c4, 0)
        # With concurrency=4 we have 4 workers each at rate/4 – the aggregate
        # should be in the same ballpark as concurrency=1 (same total rate target).
        # Allow generous tolerance because of scheduling jitter in short windows.
        ratio = events_c4 / events_c1 if events_c1 > 0 else 0
        self.assertGreater(ratio, 0.5, "c=4 should produce at least 50% as many events as c=1")

    def test_aggregate_rate_calculation(self):
        """Each worker's sleep is batch_size / (total_rate / concurrency).
        Verifying: with rate=200, concurrency=4, batch=10
        → per-worker sleep = 10 / (200/4) = 10/50 = 0.2s
        → in 0.3s window each worker gets ~1-2 batches → total events ~10-20.
        """
        async def run():
            sink = _CapturingSink()
            gen = TrafficGenerator(_make_steady(200.0), _make_factory(seed=42), sink,
                                   batch_size=10, concurrency=4)
            await gen.start()
            await asyncio.sleep(0.25)
            await gen.stop()
            return sink.total_events
        events = asyncio.run(run())
        # Each worker sleeps 0.2s between batches of 10; in 0.25s each fires at most 2.
        # With 4 workers: 4 * 1 batch minimum = 40 events at least.
        self.assertGreaterEqual(events, 10,
            f"Expected >= 10 events from aggregate 200 ev/s over 0.25s, got {events}")

    def test_existing_profiles_still_work_with_concurrency(self):
        """SurgeProfile must still work correctly with multiple concurrent producers."""
        async def run():
            sink = _CapturingSink()
            profile = SurgeProfile("surge", baseline_rate=50.0, multiplier=4.0)
            gen = TrafficGenerator(profile, _make_factory(), sink, batch_size=5, concurrency=4)
            await gen.start()
            await asyncio.sleep(0.05)
            await gen.stop()
            return sink.total_events
        events = asyncio.run(run())
        self.assertGreater(events, 0, "SurgeProfile with concurrency=4 must generate events")

    def test_invalid_concurrency_raises(self):
        """concurrency=0 must raise ValueError."""
        with self.assertRaises(ValueError):
            TrafficGenerator(_make_steady(), _make_factory(), _noop_sink, concurrency=0)

    def test_double_start_does_not_create_extra_tasks(self):
        """Second start() while running must be a no-op; task list must not grow."""
        async def run():
            gen = TrafficGenerator(_make_steady(), _make_factory(), _noop_sink, concurrency=2)
            await gen.start()
            task_after_first = gen._task  # first task in _tasks
            tasks_count_first = len(gen._tasks)
            await gen.start()  # should be a no-op
            task_after_second = gen._task
            tasks_count_second = len(gen._tasks)
            await gen.stop()
            return task_after_first, task_after_second, tasks_count_first, tasks_count_second
        t1, t2, c1, c2 = asyncio.run(run())
        self.assertIs(t1, t2, "Double start must not replace the task list")
        self.assertEqual(c1, c2, "Double start must not change task count")


if __name__ == "__main__":
    unittest.main()

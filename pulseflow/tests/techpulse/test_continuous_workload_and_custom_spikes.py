"""Unit & integration tests for TechPulse Continuous Baseline Traffic and Custom Spike Engine.

Covers all 12 required test cases:
1.  test_baseline_generator_starts
2.  test_baseline_rate_control
3.  test_preset_spike_changes_target_rate
4.  test_spike_returns_to_baseline
5.  test_custom_rate_validation
6.  test_custom_spike_duration
7.  test_custom_event_count
8.  test_custom_run_returns_to_baseline
9.  test_no_duplicate_generator_tasks
10. test_unique_event_ids
11. test_pulseflow_url_configuration
12. test_connection_failure_handling
"""

import asyncio
import os
import time
import unittest
from typing import List
from unittest.mock import patch

from contracts.events import EventBatch
from techpulse import config
from techpulse.client.pulseflow_client import PulseFlowClient, PulseFlowClientError
from techpulse.generator.event_factory import EventFactory
from techpulse.generator.traffic_generator import GeneratorStats, TrafficGenerator
from techpulse.generator.traffic_profiles import (
    DynamicWorkloadProfile,
    SpikeMode,
    TrafficState,
)


class CapturingSink:
    """Async test sink capturing received batches and latency."""

    def __init__(self, delay: float = 0.0) -> None:
        self.batches: List[EventBatch] = []
        self.delay = delay

    async def __call__(self, batch: EventBatch) -> None:
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        self.batches.append(batch)

    @property
    def total_events(self) -> int:
        return sum(len(b) for b in self.batches)


class FailingSink:
    """Async test sink that simulates connection failures."""

    def __init__(self) -> None:
        self.attempts: int = 0

    async def __call__(self, batch: EventBatch) -> None:
        self.attempts += 1
        raise PulseFlowClientError("Connection refused: simulated PulseFlow offline")


class TestContinuousWorkloadAndCustomSpikes(unittest.IsolatedAsyncioTestCase):
    """Test suite verifying continuous baseline traffic, custom spikes, and network resilience."""

    def setUp(self) -> None:
        self.factory = EventFactory(seed=42)

    # ------------------------------------------------------------------
    # 1. Baseline Generator Starts Automatically
    # ------------------------------------------------------------------
    async def test_baseline_generator_starts(self) -> None:
        """Generator starts immediately in BASELINE state at ~100 ev/s without clicking any button."""
        profile = DynamicWorkloadProfile(baseline_rate=100.0)
        sink = CapturingSink()
        gen = TrafficGenerator(profile, self.factory, sink, batch_size=10, concurrency=2)

        # Before start
        self.assertFalse(gen.is_running)
        self.assertEqual(profile.state, TrafficState.BASELINE)
        self.assertEqual(profile.current_target_rate, 100.0)

        # Start generator
        await gen.start()
        self.assertTrue(gen.is_running)
        await asyncio.sleep(0.08)

        stats = gen.stats()
        self.assertTrue(stats.running)
        self.assertEqual(stats.state, "BASELINE")
        self.assertEqual(stats.current_rate, 100.0)
        self.assertGreater(stats.events_delivered, 0)
        self.assertGreater(stats.events_generated, 0)

        await gen.stop()
        self.assertFalse(gen.is_running)

    # ------------------------------------------------------------------
    # 2. Baseline Rate Control
    # ------------------------------------------------------------------
    async def test_baseline_rate_control(self) -> None:
        """Rate control delivers batches pacing toward the target rate."""
        profile = DynamicWorkloadProfile(baseline_rate=200.0)
        sink = CapturingSink()
        gen = TrafficGenerator(profile, self.factory, sink, batch_size=10, concurrency=2)

        await gen.start()
        await asyncio.sleep(0.08)
        await gen.stop()

        stats = gen.stats()
        self.assertEqual(stats.current_rate, 200.0)
        self.assertGreater(sink.total_events, 0)
        self.assertGreaterEqual(stats.events_delivered, sink.total_events)

    # ------------------------------------------------------------------
    # 3. Preset Spike Changes Target Rate
    # ------------------------------------------------------------------
    async def test_preset_spike_changes_target_rate(self) -> None:
        """Preset multipliers modify the single generator's target rate without starting a new loop."""
        profile = DynamicWorkloadProfile(baseline_rate=100.0)
        sink = CapturingSink()
        gen = TrafficGenerator(profile, self.factory, sink, batch_size=5, concurrency=1)

        await gen.start()
        self.assertEqual(profile.target_rate(0.0), 100.0)

        # Apply 5x preset -> 500 ev/s
        profile.set_preset_spike(5.0, duration=10.0)
        self.assertEqual(profile.state, TrafficState.SPIKE_ACTIVE)
        self.assertEqual(profile.multiplier, 5.0)
        self.assertEqual(profile.target_rate(0.0), 500.0)
        self.assertEqual(gen.stats().state, "SPIKE_ACTIVE")

        # Apply 20x preset -> 2000 ev/s
        profile.set_preset_spike(20.0, duration=10.0)
        self.assertEqual(profile.multiplier, 20.0)
        self.assertEqual(profile.target_rate(0.0), 2000.0)

        await gen.stop()

    # ------------------------------------------------------------------
    # 4. Spike Returns to Baseline (Never 0)
    # ------------------------------------------------------------------
    async def test_spike_returns_to_baseline(self) -> None:
        """Ending a spike returns target rate to baseline (100 ev/s), never zero."""
        profile = DynamicWorkloadProfile(baseline_rate=100.0)
        profile.set_preset_spike(20.0, duration=10.0)
        self.assertEqual(profile.target_rate(0.0), 2000.0)

        # Recover
        recovered_rate = profile.recover_to_baseline()
        self.assertEqual(recovered_rate, 100.0)
        self.assertEqual(profile.state, TrafficState.BASELINE)
        self.assertEqual(profile.multiplier, 1.0)
        self.assertEqual(profile.target_rate(0.0), 100.0)
        self.assertNotEqual(profile.target_rate(0.0), 0.0)

    # ------------------------------------------------------------------
    # 5. Custom Rate Validation
    # ------------------------------------------------------------------
    def test_custom_rate_validation(self) -> None:
        """Validates rate > 0, duration > 0, rate <= MAX_CUSTOM_RATE."""
        profile = DynamicWorkloadProfile(baseline_rate=100.0, max_custom_rate=50000.0)

        # Valid custom rates
        self.assertEqual(profile.set_custom_spike(500.0, 15.0), 500.0)
        self.assertEqual(profile.set_custom_spike(3500.0, 20.0), 3500.0)
        self.assertEqual(profile.set_custom_spike(5000.0, 30.0), 5000.0)
        self.assertEqual(profile.set_custom_spike(50000.0, 10.0), 50000.0)

        # Invalid rates
        with self.assertRaises(ValueError):
            profile.set_custom_spike(0.0, 15.0)
        with self.assertRaises(ValueError):
            profile.set_custom_spike(-100.0, 15.0)
        with self.assertRaises(ValueError):
            profile.set_custom_spike(50001.0, 15.0)  # Exceeds max
        with self.assertRaises(ValueError):
            profile.set_custom_spike(5000.0, 0.0)  # Non-positive duration
        with self.assertRaises(ValueError):
            profile.set_custom_spike(5000.0, -5.0)

    # ------------------------------------------------------------------
    # 6. Custom Spike Duration Auto-reversion
    # ------------------------------------------------------------------
    async def test_custom_spike_duration(self) -> None:
        """Custom spike automatically reverts to baseline once duration expires."""
        profile = DynamicWorkloadProfile(baseline_rate=100.0)
        # Short duration of 0.05 seconds for fast test execution
        profile.set_custom_spike(target_rate=5000.0, duration=0.05)
        self.assertEqual(profile.state, TrafficState.SPIKE_ACTIVE)
        self.assertEqual(profile.target_rate(0.0), 5000.0)

        # Wait past duration
        await asyncio.sleep(0.08)

        # target_rate checks elapsed duration and auto-reverts to baseline
        rate_after = profile.target_rate(0.0)
        self.assertEqual(rate_after, 100.0)
        self.assertEqual(profile.state, TrafficState.BASELINE)

    # ------------------------------------------------------------------
    # 7. Custom Event Count
    # ------------------------------------------------------------------
    def test_custom_event_count(self) -> None:
        """Custom event run sets target count and max rate properly."""
        profile = DynamicWorkloadProfile(baseline_rate=100.0)
        profile.set_custom_event_run(total_events=10000, max_rate=2500.0)

        self.assertEqual(profile.state, TrafficState.SPIKE_ACTIVE)
        self.assertEqual(profile.spike_mode, SpikeMode.CUSTOM_COUNT)
        self.assertEqual(profile.events_target, 10000)
        self.assertEqual(profile.target_rate(0.0), 2500.0)

        # Partial deliveries
        profile.record_events_delivered(4000)
        self.assertEqual(profile.events_spiked, 4000)
        self.assertEqual(profile.state, TrafficState.SPIKE_ACTIVE)

        # Invalid configurations
        with self.assertRaises(ValueError):
            profile.set_custom_event_run(total_events=0, max_rate=1000.0)
        with self.assertRaises(ValueError):
            profile.set_custom_event_run(total_events=1000, max_rate=-50.0)

    # ------------------------------------------------------------------
    # 8. Custom Run Returns to Baseline
    # ------------------------------------------------------------------
    async def test_custom_run_returns_to_baseline(self) -> None:
        """When requested event count completes, generator automatically reverts to baseline."""
        profile = DynamicWorkloadProfile(baseline_rate=100.0)
        sink = CapturingSink()
        gen = TrafficGenerator(profile, self.factory, sink, batch_size=10, concurrency=1)

        # Configure custom run of exactly 30 events at 1000 ev/s
        profile.set_custom_event_run(total_events=30, max_rate=1000.0)
        self.assertEqual(profile.state, TrafficState.SPIKE_ACTIVE)

        await gen.start()

        # Wait for batches to be delivered
        for _ in range(50):
            if profile.state == TrafficState.BASELINE:
                break
            await asyncio.sleep(0.01)

        await gen.stop()

        # Generator must have returned to baseline and continue running baseline rate
        self.assertEqual(profile.state, TrafficState.BASELINE)
        self.assertEqual(profile.current_target_rate, 100.0)
        self.assertGreaterEqual(sink.total_events, 30)

    # ------------------------------------------------------------------
    # 9. No Duplicate Generator Tasks
    # ------------------------------------------------------------------
    async def test_no_duplicate_generator_tasks(self) -> None:
        """Calling start() repeatedly or changing spikes never spawns duplicate loops."""
        profile = DynamicWorkloadProfile(baseline_rate=100.0)
        sink = CapturingSink()
        gen = TrafficGenerator(profile, self.factory, sink, batch_size=10, concurrency=2)

        await gen.start()
        tasks_count_1 = len(gen._tasks)
        task_ref_1 = gen._tasks[0]

        # Duplicate start calls must be no-ops
        await gen.start()
        await gen.start()
        self.assertEqual(len(gen._tasks), tasks_count_1)
        self.assertIs(gen._tasks[0], task_ref_1)

        # Triggering spikes modifies target rate on the same generator
        profile.set_preset_spike(20.0)
        self.assertEqual(len(gen._tasks), tasks_count_1)

        profile.recover_to_baseline()
        self.assertEqual(len(gen._tasks), tasks_count_1)

        await gen.stop()
        self.assertEqual(len(gen._tasks), 0)

    # ------------------------------------------------------------------
    # 10. Unique Event IDs and Realistic Payload Schema
    # ------------------------------------------------------------------
    async def test_unique_event_ids(self) -> None:
        """Every generated event has a unique event_id and conforms to contracts."""
        sink = CapturingSink()
        profile = DynamicWorkloadProfile(baseline_rate=1000.0)
        gen = TrafficGenerator(profile, self.factory, sink, batch_size=25, concurrency=2)

        await gen.start()
        await asyncio.sleep(0.05)
        await gen.stop()

        seen_ids = set()
        event_types = set()
        for batch in sink.batches:
            for event in batch:
                self.assertNotIn(event.event_id, seen_ids, "event_id must be unique")
                seen_ids.add(event.event_id)
                event_types.add(event.event_type)
                self.assertIsNotNone(event.timestamp)
                self.assertIsInstance(event.payload, dict)

        # Verify priority event mix occurred (e.g. ORDER, PAYMENT, etc.)
        self.assertGreater(len(seen_ids), 0)
        self.assertGreater(len(event_types), 1)

    # ------------------------------------------------------------------
    # 11. PulseFlow URL Configuration
    # ------------------------------------------------------------------
    def test_pulseflow_url_configuration(self) -> None:
        """PULSEFLOW_BASE_URL is configurable via environment variable."""
        with patch.dict(os.environ, {"PULSEFLOW_BASE_URL": "http://192.168.1.50:8000"}):
            url = config._get_base_url()
            self.assertEqual(url, "http://192.168.1.50:8000")

        with patch.dict(os.environ, {"PULSEFLOW_BASE_URL": "http://10.0.0.12:9000/events"}):
            # Strips trailing /events cleanly
            url = config._get_base_url()
            self.assertEqual(url, "http://10.0.0.12:9000")

        # Client respects configured base URL
        client = PulseFlowClient(base_url="http://192.168.1.20:8000")
        self.assertEqual(client._base_url, "http://192.168.1.20:8000")
        self.assertEqual(client._events_url, "http://192.168.1.20:8000/events/batch")

    # ------------------------------------------------------------------
    # 12. Connection Failure Handling
    # ------------------------------------------------------------------
    async def test_connection_failure_handling(self) -> None:
        """When PulseFlow is offline, generator tracks failed events and does not crash."""
        failing_sink = FailingSink()
        profile = DynamicWorkloadProfile(baseline_rate=500.0)
        gen = TrafficGenerator(profile, self.factory, failing_sink, batch_size=10, concurrency=1)

        await gen.start()
        await asyncio.sleep(0.05)
        await gen.stop()

        stats = gen.stats()
        # Generator survived and accurately recorded attempts and failures
        self.assertGreater(stats.errors, 0)
        self.assertGreater(stats.events_failed, 0)
        self.assertEqual(stats.events_delivered, 0)
        self.assertGreater(failing_sink.attempts, 0)


if __name__ == "__main__":
    unittest.main()

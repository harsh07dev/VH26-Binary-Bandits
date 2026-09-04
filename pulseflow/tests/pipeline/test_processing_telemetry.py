"""Tests for real runtime latency and processing-rate telemetry."""

import asyncio
import time
import pytest

from contracts.events import Event
from contracts.priorities import Priority
from contracts.metrics import SystemSnapshot, QueueMetrics, WorkerMetrics
from pipeline.processing.telemetry import ProcessingTelemetryTracker, processing_telemetry
from pipeline.processing.event_processor import EventProcessor
from pipeline.storage.database import DatabaseManager
from pipeline.storage.repository import EventRepository
from adaptive.pressure.pressure_calculator import PressureCalculator


@pytest.fixture(autouse=True)
def clean_telemetry():
    processing_telemetry.reset()
    yield
    processing_telemetry.reset()


@pytest.fixture
async def test_db():
    db = DatabaseManager(db_path=":memory:")
    await db.init_db()
    yield db
    await db.close()


@pytest.fixture
def test_repo(test_db):
    return EventRepository(db=test_db)


def test_telemetry_rate_calculation_and_pruning():
    tracker = ProcessingTelemetryTracker(window_sec=5.0)

    now = 1000.0
    # Record 100 events at t=1000.0
    tracker.record_batch([10.0] * 100, priority=Priority.NORMAL, now=now)
    # Check rate at t=1002.0 (2 seconds elapsed -> 100 events / 2s = 50.0 ev/s)
    rate = tracker.get_processing_rate(now=1002.0)
    assert rate == 50.0
    assert tracker.get_processed_count() == 100

    # Check latency
    avg_lat = tracker.get_avg_latency_ms(now=1002.0)
    assert avg_lat == 10.0

    # Advance time beyond 5-second window (t=1006.0)
    # The 100 events should be pruned from the active window
    rate_after_window = tracker.get_processing_rate(now=1006.0)
    assert rate_after_window == 0.0
    # Cumulative count is preserved
    assert tracker.get_processed_count() == 100


def test_telemetry_per_lane_latency():
    tracker = ProcessingTelemetryTracker(window_sec=10.0)

    now = 1000.0
    # Critical: 5ms
    tracker.record(latency_ms=5.0, priority=Priority.CRITICAL, now=now)
    # Normal: 20ms
    tracker.record(latency_ms=20.0, priority=Priority.NORMAL, now=now)
    # Best effort: 50ms
    tracker.record(latency_ms=50.0, priority=Priority.BEST_EFFORT, now=now)

    assert tracker.get_avg_latency_ms(Priority.CRITICAL, now=now) == 5.0
    assert tracker.get_avg_latency_ms(Priority.NORMAL, now=now) == 20.0
    assert tracker.get_avg_latency_ms(Priority.BEST_EFFORT, now=now) == 50.0
    assert tracker.get_avg_latency_ms(now=now) == 25.0  # (5 + 20 + 50) / 3


@pytest.mark.asyncio
async def test_event_processor_records_real_latency(test_repo):
    processor = EventProcessor(repository=test_repo, telemetry=processing_telemetry)

    now = time.time()
    # Event ingested 45ms ago
    event = Event(
        event_type="ORDER",
        received_at=now - 0.045
    )

    result = await processor.process_single(event, mode="STREAM")
    assert result.latency_ms >= 45.0

    # Verify telemetry tracker captured it
    avg_lat = processing_telemetry.get_avg_latency_ms()
    assert avg_lat >= 45.0
    assert processing_telemetry.get_processed_count() == 1
    assert processing_telemetry.get_processing_rate() > 0.0


@pytest.mark.asyncio
async def test_event_processor_records_batch_latency(test_repo):
    processor = EventProcessor(repository=test_repo, telemetry=processing_telemetry)

    now = time.time()
    events = [
        Event(event_type="CART_ADD", received_at=now - 0.020),
        Event(event_type="CART_ADD", received_at=now - 0.030),
    ]

    results = await processor.process_batch(events, mode="BATCH")
    assert len(results) == 2

    avg_lat = processing_telemetry.get_avg_latency_ms(Priority.NORMAL)
    assert 20.0 <= avg_lat <= 40.0
    assert processing_telemetry.get_processed_count() == 2


def test_system_snapshot_and_pressure_calculation_integration():
    # Verify SystemSnapshot receives real latency and processing rate
    # and PressureCalculator properly uses them
    snapshot = SystemSnapshot(
        queues=QueueMetrics(critical=100, normal=500, best_effort=500),
        workers=WorkerMetrics(utilization=0.75),
        avg_latency_ms=250.0,
        processing_rate=200.0,
    )

    assert snapshot.avg_latency_ms == 250.0
    assert snapshot.processing_rate == 200.0

    # Ingress rate = 300 ev/s (greater than processing rate)
    pressure = PressureCalculator.calculate(snapshot, ingress_rate=300.0)

    # Latency factor should be 250 / 1000 = 0.25
    # Rate factor should be min(1.0, 300 / 400) = 0.75
    # Latency and processing rate are non-zero and actively driving the score
    assert pressure.latency == 250.0
    assert pressure.processingRate == 200.0
    assert pressure.pressureScore > 0.0

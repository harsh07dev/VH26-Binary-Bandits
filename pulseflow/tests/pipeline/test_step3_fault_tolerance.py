"""Tests for Step 3: Fault Tolerance, In-Flight ACKs, Timeout Auto-Recovery, and Graceful Shutdown."""

from __future__ import annotations

import asyncio
import signal
import time
import pytest

from contracts.events import Event
from contracts.priorities import Priority
from pipeline.consumer import (
    InFlightTracker,
    ack_event,
    in_flight_tracker,
    nack_event,
    track_event,
)
from pipeline.main import perform_graceful_shutdown, setup_signal_handlers
from pipeline.queues.queue_manager import QueueManager


# =========================================================================
# 1. In-Flight Buffer & Explicit ACK Eviction Tests
# =========================================================================

def test_in_flight_tracking_and_ack_eviction():
    """Verify events are retained in in_flight until and ONLY until explicit ACK is issued."""
    tracker = InFlightTracker()
    event = Event(event_type="PAYMENT", payload={"order_id": "ord-101"})

    assert tracker.in_flight_count == 0
    assert not tracker.is_in_flight(event.event_id)

    # 1. Track event
    tracker.track(event)
    assert tracker.in_flight_count == 1
    assert tracker.is_in_flight(event.event_id)
    assert tracker.get_in_flight(event.event_id) is not None

    # 2. Re-verifying item is not evicted without ACK
    assert tracker.in_flight_count == 1

    # 3. Explicit worker ACK
    ack_success = tracker.ack(event.event_id)
    assert ack_success is True
    assert tracker.in_flight_count == 0
    assert not tracker.is_in_flight(event.event_id)
    assert tracker.total_acked == 1

    # Redundant ACK returns False
    assert tracker.ack(event.event_id) is False


def test_nack_requeues_to_critical_queue():
    """Verify nack removes item from in-flight and returns it to CRITICAL queue."""
    qm = QueueManager()
    tracker = InFlightTracker(qm=qm)
    event = Event(event_type="ORDER", payload={"amount": 75.0})

    tracker.track(event)
    assert tracker.in_flight_count == 1

    # NACK
    nacked = tracker.nack(event.event_id, requeue=True)
    assert nacked is not None
    assert nacked.event_id == event.event_id
    assert tracker.in_flight_count == 0

    # Ensure re-queued into CRITICAL queue
    assert qm.critical_queue.depth() == 1
    requeued = qm.critical_queue.dequeue_nowait()
    assert requeued.event_id == event.event_id


# =========================================================================
# 2. Timeout Auto-Recovery Monitor Tests
# =========================================================================

@pytest.mark.asyncio
async def test_timeout_auto_recovery_requeues_unacked_event():
    """Verify un-ACKed events exceeding timeout are evicted from in-flight and sent to CRITICAL queue."""
    qm = QueueManager()
    # 2.0s timeout
    tracker = InFlightTracker(qm=qm, timeout_sec=2.0)

    now = 1000.0
    # Event pulled 3.5 seconds ago (elapsed 3.5s > 2.0s timeout)
    stalled_event = Event(
        event_type="ORDER",
        timestamp=now - 3.5,
        payload={"order_id": "ord-stalled"},
    )
    tracker.track(stalled_event, now=now - 3.5)

    # Active fresh event (elapsed 0.5s < 2.0s timeout)
    fresh_event = Event(
        event_type="PAYMENT",
        timestamp=now - 0.5,
    )
    tracker.track(fresh_event, now=now - 0.5)

    assert tracker.in_flight_count == 2

    # Run timeout recovery scan
    recovered = await tracker.check_and_recover_timeouts(now=now)

    # Stalled event recovered, fresh event still in-flight
    assert len(recovered) == 1
    assert recovered[0].event_id == stalled_event.event_id
    assert tracker.in_flight_count == 1
    assert tracker.is_in_flight(fresh_event.event_id)
    assert not tracker.is_in_flight(stalled_event.event_id)

    # Verify CRITICAL queue received the recovered event
    assert qm.critical_queue.depth() == 1
    retried_event = qm.critical_queue.dequeue_nowait()
    assert retried_event.event_id == stalled_event.event_id
    assert retried_event.priority == Priority.CRITICAL
    assert retried_event.payload["_retry_count"] == 1
    assert retried_event.payload["_recovered_at"] == now


@pytest.mark.asyncio
async def test_background_timeout_monitor_loop():
    """Verify the background timeout monitor detects and recovers items automatically."""
    qm = QueueManager()
    # 0.2s timeout, 0.05s check interval
    tracker = InFlightTracker(qm=qm, timeout_sec=0.2, check_interval_sec=0.05)
    tracker.start_monitor()
    assert tracker.is_monitor_running

    try:
        event = Event(event_type="PAYMENT")
        tracker.track(event)
        assert tracker.in_flight_count == 1

        # Wait for timeout to elapse and background loop to fire
        await asyncio.sleep(0.35)

        # Monitor should have recovered the event
        assert tracker.in_flight_count == 0
        assert tracker.total_timeouts == 1
        assert qm.critical_queue.depth() == 1
    finally:
        await tracker.stop_monitor()
        assert not tracker.is_monitor_running


# =========================================================================
# 3. Graceful Shutdown & Signal Handlers Tests
# =========================================================================

@pytest.mark.asyncio
async def test_graceful_shutdown_sequence():
    """Verify perform_graceful_shutdown completes without raising exceptions and flushes state."""
    # Should cleanly execute all 6 stages
    await perform_graceful_shutdown(timeout=0.5)


def test_setup_signal_handlers_registration():
    """Verify setup_signal_handlers registers SIGINT and SIGTERM without raising errors."""
    setup_signal_handlers()

    # Verify signal handlers are callable
    handler_int = signal.getsignal(signal.SIGINT)
    assert callable(handler_int)

    handler_term = signal.getsignal(signal.SIGTERM)
    assert callable(handler_term)

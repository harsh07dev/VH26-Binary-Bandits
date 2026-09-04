import pytest
import asyncio
from contracts.events import Event
from contracts.priorities import Priority
from adaptive.queues.adaptive_queue import AdaptiveQueueRouter

@pytest.fixture(autouse=True)
def clear_queues():
    """Ensure queues are empty before and after each test."""
    AdaptiveQueueRouter.clear_all()
    yield
    AdaptiveQueueRouter.clear_all()

@pytest.mark.asyncio
async def test_correct_routing_and_priority_isolation():
    # Create events
    critical_event = Event(event_type="ORDER")
    normal_event = Event(event_type="CART_ADD")
    best_effort_event = Event(event_type="CLICK")
    
    # Route events
    await AdaptiveQueueRouter.route_event(critical_event)
    await AdaptiveQueueRouter.route_event(normal_event)
    await AdaptiveQueueRouter.route_event(best_effort_event)
    
    # Check metrics / depths are isolated
    metrics = AdaptiveQueueRouter.get_metrics()
    assert metrics["criticalQueueDepth"] == 1
    assert metrics["normalQueueDepth"] == 1
    assert metrics["bestEffortQueueDepth"] == 1
    
    # Dequeue and verify
    dequeued_critical = await AdaptiveQueueRouter.dequeue(Priority.CRITICAL)
    assert dequeued_critical.event_id == critical_event.event_id
    
    dequeued_normal = await AdaptiveQueueRouter.dequeue(Priority.NORMAL)
    assert dequeued_normal.event_id == normal_event.event_id
    
    dequeued_best = await AdaptiveQueueRouter.dequeue(Priority.BEST_EFFORT)
    assert dequeued_best.event_id == best_effort_event.event_id

def test_enqueue_dequeue_nowait():
    event = Event(event_type="PAYMENT")
    
    # Enqueue sync
    AdaptiveQueueRouter.route_event_nowait(event)
    
    # Check depth
    metrics = AdaptiveQueueRouter.get_metrics()
    assert metrics["criticalQueueDepth"] == 1
    
    # Dequeue sync
    dequeued = AdaptiveQueueRouter.dequeue_nowait(Priority.CRITICAL)
    assert dequeued.event_id == event.event_id
    
    metrics = AdaptiveQueueRouter.get_metrics()
    assert metrics["criticalQueueDepth"] == 0

@pytest.mark.asyncio
async def test_critical_event_protection():
    """Verify that a CRITICAL event routed to the critical queue can be successfully retrieved 
    and is isolated from normal/best-effort queues, fulfilling the baseline safety requirement."""
    event = Event(event_type="PAYMENT")
    
    await AdaptiveQueueRouter.route_event(event)
    metrics = AdaptiveQueueRouter.get_metrics()
    
    assert metrics["criticalQueueDepth"] == 1
    assert metrics["normalQueueDepth"] == 0
    assert metrics["bestEffortQueueDepth"] == 0
    
    # The queue manager uses a dedicated CriticalQueue, which prevents it 
    # from being dropped by normal queue overflow logic.
    assert (await AdaptiveQueueRouter.dequeue(Priority.CRITICAL)).event_id == event.event_id

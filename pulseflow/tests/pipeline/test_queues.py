"""Tests for the PulseFlow pipeline queue layer and QueueManager integration."""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from contracts.priorities import Priority
from contracts.events import Event
from contracts.metrics import QueueMetrics
from pipeline.queues import (
    CriticalQueue,
    NormalQueue,
    BestEffortQueue,
    QueueManager,
    queue_manager,
)
from pipeline.ingestion.api import router, set_enqueue_handler


# ---------------------------------------------------------------------------
# Individual Queue Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_critical_queue_operations():
    """Verify basic CriticalQueue lifecycle: enqueue, depth, dequeue, clear."""
    q = CriticalQueue()
    assert q.priority == Priority.CRITICAL
    assert q.depth() == 0
    assert q.is_empty()

    evt1 = Event(event_id="crit-1", event_type="ORDER")
    evt2 = Event(event_id="crit-2", event_type="PAYMENT")

    await q.enqueue(evt1)
    await q.enqueue(evt2)

    assert q.depth() == 2
    assert len(q) == 2
    assert not q.is_empty()
    assert q.total_enqueued == 2

    # Verify FIFO retrieval
    popped1 = await q.dequeue()
    assert popped1.event_id == "crit-1"
    assert popped1.priority == Priority.CRITICAL
    assert q.depth() == 1

    popped2 = await q.get()
    assert popped2.event_id == "crit-2"
    assert q.depth() == 0
    assert q.is_empty()
    assert q.total_dequeued == 2


@pytest.mark.asyncio
async def test_normal_queue_operations():
    """Verify NormalQueue enqueue, dequeue, and clear."""
    q = NormalQueue()
    assert q.priority == Priority.NORMAL

    evt = Event(event_id="norm-1", event_type="CART_ADD")
    await q.enqueue(evt)
    assert q.depth() == 1

    drained = q.clear()
    assert drained == 1
    assert q.depth() == 0
    assert q.is_empty()


@pytest.mark.asyncio
async def test_best_effort_queue_operations():
    """Verify BestEffortQueue enqueue, dequeue, and clear."""
    q = BestEffortQueue()
    assert q.priority == Priority.BEST_EFFORT

    evt = Event(event_id="be-1", event_type="CLICK")
    q.enqueue_nowait(evt)
    assert q.depth() == 1

    popped = q.dequeue_nowait()
    assert popped.event_id == "be-1"
    assert q.depth() == 0


# ---------------------------------------------------------------------------
# QueueManager Routing Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_queue_manager_automatic_routing_all_7_events():
    """Test that QueueManager routes all 7 event types to their correct priority queue."""
    qm = QueueManager()

    test_matrix = [
        ("ORDER", Priority.CRITICAL),
        ("PAYMENT", Priority.CRITICAL),
        ("CART_ADD", Priority.NORMAL),
        ("INVENTORY_UPDATE", Priority.NORMAL),
        ("CLICK", Priority.BEST_EFFORT),
        ("PAGE_VIEW", Priority.BEST_EFFORT),
        ("LOG", Priority.BEST_EFFORT),
    ]

    for event_type, expected_priority in test_matrix:
        evt = Event(event_id=f"evt-{event_type}", event_type=event_type)
        await qm.enqueue(evt)

    # 2 Critical, 2 Normal, 3 Best-Effort
    assert qm.depth(Priority.CRITICAL) == 2
    assert qm.depth(Priority.NORMAL) == 2
    assert qm.depth(Priority.BEST_EFFORT) == 3
    assert qm.total_depth() == 7

    # Verify QueueMetrics snapshot
    metrics = qm.queue_metrics()
    assert isinstance(metrics, QueueMetrics)
    assert metrics.critical == 2
    assert metrics.normal == 2
    assert metrics.best_effort == 3
    assert metrics.total_depth == 7

    # Verify FIFO dequeue from respective lanes
    crit1 = await qm.get(Priority.CRITICAL)
    assert crit1.event_type == "ORDER"
    crit2 = await qm.get(Priority.CRITICAL)
    assert crit2.event_type == "PAYMENT"
    assert qm.depth(Priority.CRITICAL) == 0

    norm1 = await qm.get(Priority.NORMAL)
    assert norm1.event_type == "CART_ADD"
    norm2 = await qm.get(Priority.NORMAL)
    assert norm2.event_type == "INVENTORY_UPDATE"
    assert qm.depth(Priority.NORMAL) == 0

    be1 = await qm.get(Priority.BEST_EFFORT)
    assert be1.event_type == "CLICK"
    be2 = await qm.get(Priority.BEST_EFFORT)
    assert be2.event_type == "PAGE_VIEW"
    be3 = await qm.get(Priority.BEST_EFFORT)
    assert be3.event_type == "LOG"
    assert qm.depth(Priority.BEST_EFFORT) == 0

    assert qm.total_depth() == 0
    assert qm.is_empty()


@pytest.mark.asyncio
async def test_queue_manager_string_priority_resolution():
    """Verify depth() and get() accept string priority representations."""
    qm = QueueManager()
    evt = Event(event_type="ORDER")
    await qm.enqueue(evt)

    assert qm.depth("CRITICAL") == 1
    assert qm.depth("critical") == 1
    popped = await qm.get("CRITICAL")
    assert popped.event_type == "ORDER"
    assert qm.depth("CRITICAL") == 0


@pytest.mark.asyncio
async def test_queue_manager_clear():
    """Verify clear drains all 3 priority queues."""
    qm = QueueManager()
    await qm.enqueue(Event(event_type="ORDER"))
    await qm.enqueue(Event(event_type="CART_ADD"))
    await qm.enqueue(Event(event_type="CLICK"))

    assert qm.total_depth() == 3
    drained = qm.clear()
    assert drained["CRITICAL"] == 1
    assert drained["NORMAL"] == 1
    assert drained["BEST_EFFORT"] == 1
    assert qm.total_depth() == 0


# ---------------------------------------------------------------------------
# Ingestion API Integration Tests (POST /events and POST /events/batch)
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    test_app = FastAPI()
    test_app.include_router(router)
    return test_app


@pytest.fixture(autouse=True)
def clean_shared_queue_manager():
    """Reset shared singleton queue manager before and after each test."""
    queue_manager.clear()
    set_enqueue_handler(queue_manager.enqueue)
    yield
    queue_manager.clear()
    set_enqueue_handler(queue_manager.enqueue)


@pytest.mark.asyncio
async def test_post_single_event_actually_enqueues(app):
    """Verify POST /events actually stores the event in the appropriate lane."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.post("/events", json={"event_id": "api-order-1", "event_type": "ORDER"})
        assert res.status_code == 202

    assert queue_manager.depth(Priority.CRITICAL) == 1
    assert queue_manager.depth(Priority.NORMAL) == 0
    assert queue_manager.depth(Priority.BEST_EFFORT) == 0

    event = await queue_manager.get(Priority.CRITICAL)
    assert event.event_id == "api-order-1"
    assert event.priority == Priority.CRITICAL
    assert queue_manager.total_depth() == 0


@pytest.mark.asyncio
async def test_post_batch_events_enqueues_every_event(app):
    """Verify POST /events/batch enqueues each event into its correct lane."""
    transport = ASGITransport(app=app)
    batch_payload = {
        "events": [
            {"event_id": "b-ord", "event_type": "ORDER"},
            {"event_id": "b-pay", "event_type": "PAYMENT"},
            {"event_id": "b-cart", "event_type": "CART_ADD"},
            {"event_id": "b-inv", "event_type": "INVENTORY_UPDATE"},
            {"event_id": "b-clk", "event_type": "CLICK"},
            {"event_id": "b-pv", "event_type": "PAGE_VIEW"},
            {"event_id": "b-log", "event_type": "LOG"},
        ]
    }

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.post("/events/batch", json=batch_payload)
        assert res.status_code == 202
        data = res.json()
        assert data["accepted_count"] == 7

    # Validate depths in QueueManager
    assert queue_manager.depth(Priority.CRITICAL) == 2
    assert queue_manager.depth(Priority.NORMAL) == 2
    assert queue_manager.depth(Priority.BEST_EFFORT) == 3
    assert queue_manager.total_depth() == 7

    # Validate metrics
    m = queue_manager.queue_metrics()
    assert m.critical == 2
    assert m.normal == 2
    assert m.best_effort == 3
    assert m.total_depth == 7

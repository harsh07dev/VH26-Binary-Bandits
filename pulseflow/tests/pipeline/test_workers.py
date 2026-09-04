"""Tests for the PulseFlow pipeline worker layer, WorkerPool, and end-to-end integration."""

import asyncio
import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from contracts.priorities import Priority
from contracts.events import Event
from pipeline.storage.database import DatabaseManager
from pipeline.storage.repository import EventRepository
from pipeline.processing.event_processor import EventProcessor
from pipeline.queues import (
    CriticalQueue,
    NormalQueue,
    BestEffortQueue,
    QueueManager,
    queue_manager,
)
from pipeline.workers import (
    StreamWorker,
    BatchWorker,
    WorkerPool,
    WorkerState,
)
from pipeline.ingestion.api import router, set_enqueue_handler


@pytest.fixture
async def test_db():
    """In-memory SQLite database for test isolation."""
    db = DatabaseManager(db_path=":memory:")
    await db.init_db()
    yield db
    await db.close()


@pytest.fixture
def test_repo(test_db):
    return EventRepository(db=test_db)


@pytest.fixture
def test_processor(test_repo):
    return EventProcessor(repository=test_repo)


# ---------------------------------------------------------------------------
# Stream Worker Unit Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_worker_processes_event_immediately(test_processor, test_repo):
    """Verify StreamWorker immediately dequeues, processes, and persists single events."""
    q = CriticalQueue()
    worker = StreamWorker(
        worker_id="crit-stream-1",
        priority=Priority.CRITICAL,
        queue=q,
        processor=test_processor,
        poll_interval=0.05,
    )

    evt = Event(event_id="crit-e1", event_type="ORDER", payload={"price": 99.0})
    await q.enqueue(evt)
    assert q.depth() == 1

    worker.start()
    assert worker.is_running

    # Wait for queue to be consumed
    for _ in range(20):
        if q.depth() == 0 and worker.events_processed > 0:
            break
        await asyncio.sleep(0.05)

    assert q.depth() == 0
    assert worker.events_processed == 1
    assert worker.errors_count == 0

    # Verify written to SQLite
    stored = await test_repo.get_event("crit-e1")
    assert stored is not None
    assert stored["event_id"] == "crit-e1"
    assert stored["priority"] == Priority.CRITICAL.value
    assert stored["processing_mode"] == "STREAM"
    assert stored["status"] == "processed"

    await worker.stop()
    assert not worker.is_running


# ---------------------------------------------------------------------------
# Batch Worker Unit Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_worker_collects_and_processes_batch(test_processor, test_repo):
    """Verify BatchWorker gathers multiple events and processes them in a single batch."""
    q = NormalQueue()
    worker = BatchWorker(
        worker_id="norm-batch-1",
        priority=Priority.NORMAL,
        queue=q,
        processor=test_processor,
        batch_size=5,
        batch_timeout_ms=100.0,
    )

    for i in range(5):
        await q.enqueue(Event(event_id=f"norm-e{i}", event_type="CART_ADD"))

    assert q.depth() == 5
    worker.start()

    # Wait for batch processing
    for _ in range(20):
        if q.depth() == 0 and worker.events_processed >= 5:
            break
        await asyncio.sleep(0.05)

    assert q.depth() == 0
    assert worker.events_processed == 5
    assert worker.batches_processed == 1

    # Verify all 5 written to SQLite
    assert await test_repo.count_events(Priority.NORMAL) == 5

    await worker.stop()


@pytest.mark.asyncio
async def test_batch_worker_flushes_on_timeout(test_processor, test_repo):
    """Verify BatchWorker flushes partial batches when timeout expires."""
    q = BestEffortQueue()
    worker = BatchWorker(
        worker_id="be-batch-1",
        priority=Priority.BEST_EFFORT,
        queue=q,
        processor=test_processor,
        batch_size=10,  # larger than enqueued
        batch_timeout_ms=50.0,  # 50ms timeout
    )

    await q.enqueue(Event(event_id="be-flush-1", event_type="CLICK"))
    await q.enqueue(Event(event_id="be-flush-2", event_type="PAGE_VIEW"))

    worker.start()

    # Await flush
    for _ in range(20):
        if q.depth() == 0 and worker.events_processed >= 2:
            break
        await asyncio.sleep(0.05)

    assert q.depth() == 0
    assert worker.events_processed == 2
    assert worker.batches_processed == 1

    assert await test_repo.count_events(Priority.BEST_EFFORT) == 2
    await worker.stop()


# ---------------------------------------------------------------------------
# WorkerPool Dynamic Allocation & Scaling Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worker_pool_initialization_and_dynamic_scaling(test_processor):
    """Verify WorkerPool dynamic scaling between normal traffic and 20x surge allocation."""
    qm = QueueManager()
    pool = WorkerPool(qm=qm, processor=test_processor)

    # 1. Normal traffic allocation
    # Critical: 2, Normal: 4, Best-Effort: 2
    await pool.start(
        initial_allocation={
            Priority.CRITICAL: 2,
            Priority.NORMAL: 4,
            Priority.BEST_EFFORT: 2,
        }
    )

    assert pool.is_running
    alloc = pool.get_allocation()
    assert alloc[Priority.CRITICAL] == 2
    assert alloc[Priority.NORMAL] == 4
    assert alloc[Priority.BEST_EFFORT] == 2

    metrics = pool.worker_metrics()
    assert metrics.critical == 2
    assert metrics.normal == 4
    assert metrics.best_effort == 2
    assert metrics.total == 8

    # 2. Simulate 20x spike allocation prescribed by adaptive scheduler:
    # Critical: 4, Normal: 4, Best-Effort: 0
    await pool.set_allocation(
        allocation={
            Priority.CRITICAL: 4,
            Priority.NORMAL: 4,
            Priority.BEST_EFFORT: 0,
        }
    )

    spike_alloc = pool.get_allocation()
    assert spike_alloc[Priority.CRITICAL] == 4
    assert spike_alloc[Priority.NORMAL] == 4
    assert spike_alloc[Priority.BEST_EFFORT] == 0

    spike_metrics = pool.worker_metrics()
    assert spike_metrics.critical == 4
    assert spike_metrics.normal == 4
    assert spike_metrics.best_effort == 0
    assert spike_metrics.total == 8

    # 3. Scale back down to minimal
    await pool.set_allocation(
        allocation={
            Priority.CRITICAL: 1,
            Priority.NORMAL: 1,
            Priority.BEST_EFFORT: 1,
        }
    )
    min_alloc = pool.get_allocation()
    assert min_alloc[Priority.CRITICAL] == 1
    assert min_alloc[Priority.NORMAL] == 1
    assert min_alloc[Priority.BEST_EFFORT] == 1

    await pool.stop()
    assert not pool.is_running


# ---------------------------------------------------------------------------
# End-to-End Pipeline Test:
# POST /events -> Classifier -> QueueManager -> WorkerPool -> SQLite
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    test_app = FastAPI()
    test_app.include_router(router)
    return test_app


@pytest.mark.asyncio
async def test_end_to_end_pipeline_flow(app, test_processor, test_repo):
    """Verify full end-to-end event flow: Ingestion -> Queue -> Worker -> SQLite."""
    # Wire queue manager to processor via WorkerPool
    pool = WorkerPool(qm=queue_manager, processor=test_processor)
    await pool.start(
        initial_allocation={
            Priority.CRITICAL: 2,
            Priority.NORMAL: 2,
            Priority.BEST_EFFORT: 2,
        },
        batch_timeouts_ms={
            Priority.NORMAL: 30.0,
            Priority.BEST_EFFORT: 30.0,
        },
    )

    queue_manager.clear()
    set_enqueue_handler(queue_manager.enqueue)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Post single critical event
        res1 = await client.post(
            "/events",
            json={"event_id": "e2e-order-1", "event_type": "ORDER", "payload": {"total": 500}},
        )
        assert res1.status_code == 202

        # 2. Post batch of mixed events
        batch_payload = {
            "events": [
                {"event_id": "e2e-pay-2", "event_type": "PAYMENT"},
                {"event_id": "e2e-cart-3", "event_type": "CART_ADD"},
                {"event_id": "e2e-inv-4", "event_type": "INVENTORY_UPDATE"},
                {"event_id": "e2e-clk-5", "event_type": "CLICK"},
                {"event_id": "e2e-pv-6", "event_type": "PAGE_VIEW"},
            ]
        }
        res2 = await client.post("/events/batch", json=batch_payload)
        assert res2.status_code == 202

    # Await all workers consuming queues
    for _ in range(40):
        if queue_manager.total_depth() == 0 and pool.total_events_processed() >= 6:
            break
        await asyncio.sleep(0.05)

    assert queue_manager.total_depth() == 0

    # Verify events are stored in SQLite
    total_stored = await test_repo.count_events()
    assert total_stored == 6

    # Verify specific critical event
    stored_order = await test_repo.get_event("e2e-order-1")
    assert stored_order is not None
    assert stored_order["event_type"] == "ORDER"
    assert stored_order["priority"] == "CRITICAL"
    assert stored_order["status"] == "processed"
    assert stored_order["processing_mode"] == "STREAM"
    assert stored_order["latency_ms"] >= 0

    # Verify best-effort event
    stored_clk = await test_repo.get_event("e2e-clk-5")
    assert stored_clk is not None
    assert stored_clk["event_type"] == "CLICK"
    assert stored_clk["priority"] == "BEST_EFFORT"
    assert stored_clk["processing_mode"] == "BATCH"

    await pool.stop()

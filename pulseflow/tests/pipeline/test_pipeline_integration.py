"""Integration tests for the complete PulseFlow Machine 2 backend pipeline."""

import asyncio
import pytest
from httpx import AsyncClient, ASGITransport

from contracts.priorities import Priority
from pipeline.main import app, lifespan
from pipeline.storage.repository import event_repository
from pipeline.queues.queue_manager import queue_manager
from pipeline.workers.worker_pool import worker_pool


@pytest.mark.asyncio
async def test_full_pipeline_lifespan_and_endpoints():
    """Verify application startup, health, metrics, and shutdown sequences."""
    async with lifespan(app):
        # Database should be initialized, worker pool running, ingestion wired
        assert worker_pool.is_running
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Health endpoint from ingestion router
            res_health = await client.get("/health")
            assert res_health.status_code == 200
            assert res_health.json()["status"] == "healthy"

            # 2. Queue metrics endpoint
            res_qm = await client.get("/metrics/queues")
            assert res_qm.status_code == 200
            qm_data = res_qm.json()
            assert "critical" in qm_data
            assert "normal" in qm_data
            assert "best_effort" in qm_data

            # 3. Queue capacities endpoint
            res_cap = await client.get("/metrics/queues/capacities")
            assert res_cap.status_code == 200
            cap_data = res_cap.json()
            assert "capacities" in cap_data
            assert "total_depth" in cap_data

            # 4. Worker metrics endpoint
            res_wm = await client.get("/metrics/workers")
            assert res_wm.status_code == 200
            wm_data = res_wm.json()
            assert wm_data["total"] >= 6
            assert wm_data["critical"] >= 2
            assert wm_data["normal"] >= 4
            assert wm_data["best_effort"] >= 2

            # 5. Adaptive metrics endpoint
            res_ad = await client.get("/metrics/adaptive")
            assert res_ad.status_code == 200
            ad_data = res_ad.json()
            assert "metrics" in ad_data
            assert "infraMetrics" in ad_data
            assert "shedStats" in ad_data
            assert "recentEvents" in ad_data
            assert "ingress" in ad_data["metrics"]
            assert "actual_ingress_rate" in ad_data["metrics"]
            assert "actual_ingress_rate" in ad_data

    # After lifespan exit, worker pool should be gracefully stopped
    assert not worker_pool.is_running


@pytest.mark.asyncio
async def test_full_pipeline_single_event_e2e():
    """Verify single event flow: POST /events -> Priority -> Queue -> Worker -> SQLite."""
    async with lifespan(app):
        await event_repository.clear()
        queue_manager.clear()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/events",
                json={
                    "event_id": "single-order-101",
                    "event_type": "ORDER",
                    "payload": {"amount": 299.99, "customer": "vip_user"},
                },
            )
            assert res.status_code == 202
            data = res.json()
            assert data["status"] == "accepted"
            assert data["priority"] == Priority.CRITICAL.value

        # Await queue consumption by the critical stream worker
        for _ in range(30):
            if queue_manager.depth(Priority.CRITICAL) == 0 and (await event_repository.get_event("single-order-101")) is not None:
                break
            await asyncio.sleep(0.05)

        # Verify record in SQLite database
        record = await event_repository.get_event("single-order-101")
        assert record is not None
        assert record["event_id"] == "single-order-101"
        assert record["event_type"] == "ORDER"
        assert record["priority"] == "CRITICAL"
        assert record["status"] == "processed"
        assert record["processing_mode"] == "STREAM"
        assert record["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_full_pipeline_batch_events_all_7_types_e2e():
    """Verify batch flow across all 7 event types: POST /events/batch -> All Queues -> Workers -> SQLite."""
    async with lifespan(app):
        await event_repository.clear()
        queue_manager.clear()

        all_7_events = [
            # Critical lane
            {"event_id": "all7-ord-1", "event_type": "ORDER", "payload": {"item": "laptop"}},
            {"event_id": "all7-pay-2", "event_type": "PAYMENT", "payload": {"method": "cc"}},
            # Normal lane
            {"event_id": "all7-cart-3", "event_type": "CART_ADD", "payload": {"qty": 2}},
            {"event_id": "all7-inv-4", "event_type": "INVENTORY_UPDATE", "payload": {"stock": 50}},
            # Best-effort lane
            {"event_id": "all7-clk-5", "event_type": "CLICK", "payload": {"btn": "hero"}},
            {"event_id": "all7-pv-6", "event_type": "PAGE_VIEW", "payload": {"url": "/home"}},
            {"event_id": "all7-log-7", "event_type": "LOG", "payload": {"level": "info"}},
        ]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post("/events/batch", json={"events": all_7_events})
            assert res.status_code == 202
            data = res.json()
            assert data["total_received"] == 7
            assert data["accepted_count"] == 7
            assert data["priority_counts"]["CRITICAL"] == 2
            assert data["priority_counts"]["NORMAL"] == 2
            assert data["priority_counts"]["BEST_EFFORT"] == 3

        # Await all workers consuming their queues and writing to SQLite
        for _ in range(40):
            if queue_manager.total_depth() == 0 and (await event_repository.count_events()) >= 7:
                break
            await asyncio.sleep(0.05)

        assert queue_manager.total_depth() == 0

        # Verify all 7 events are persisted
        assert await event_repository.count_events() == 7

        # Verify counts per priority lane in SQLite
        assert await event_repository.count_events(Priority.CRITICAL) == 2
        assert await event_repository.count_events(Priority.NORMAL) == 2
        assert await event_repository.count_events(Priority.BEST_EFFORT) == 3

        # Verify critical processing mode is STREAM
        pay_rec = await event_repository.get_event("all7-pay-2")
        assert pay_rec["processing_mode"] == "STREAM"

        # Verify normal and best-effort processing mode is BATCH
        cart_rec = await event_repository.get_event("all7-cart-3")
        assert cart_rec["processing_mode"] == "BATCH"
        log_rec = await event_repository.get_event("all7-log-7")
        assert log_rec["processing_mode"] == "BATCH"

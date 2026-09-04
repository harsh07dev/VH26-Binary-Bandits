"""Tests for the PulseFlow ingestion API."""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from contracts.priorities import Priority
from contracts.events import Event
from pipeline.ingestion.api import router, set_enqueue_handler


@pytest.fixture
def app():
    test_app = FastAPI()
    test_app.include_router(router)
    return test_app


@pytest.fixture(autouse=True)
def clean_enqueue_handler():
    """Ensure enqueue handler is reset before each test."""
    set_enqueue_handler(None)
    yield
    set_enqueue_handler(None)


@pytest.mark.asyncio
async def test_health_check(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "pulseflow-ingestion"


@pytest.mark.asyncio
async def test_ingest_single_critical_event(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {
            "event_id": "evt-order-001",
            "event_type": "ORDER",
            "payload": {"total": 250.0, "customer_id": "cust-99"},
        }
        response = await ac.post("/events", json=payload)
    
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert data["event_id"] == "evt-order-001"
    assert data["priority"] == Priority.CRITICAL.value
    assert data["received_at"] > 0


@pytest.mark.asyncio
async def test_ingest_single_best_effort_event(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {
            "event_id": "evt-click-002",
            "event_type": "CLICK",
            "payload": {"button": "buy_now", "screen": "pdp"},
        }
        response = await ac.post("/events", json=payload)
    
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert data["priority"] == Priority.BEST_EFFORT.value


@pytest.mark.asyncio
async def test_ingest_batch_events(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {
            "events": [
                {"event_id": "b-1", "event_type": "ORDER", "payload": {}},
                {"event_id": "b-2", "event_type": "PAYMENT", "payload": {}},
                {"event_id": "b-3", "event_type": "CART_ADD", "payload": {}},
                {"event_id": "b-4", "event_type": "CLICK", "payload": {}},
                {"event_id": "b-5", "event_type": "PAGE_VIEW", "payload": {}},
            ]
        }
        response = await ac.post("/events/batch", json=payload)
    
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert data["total_received"] == 5
    assert data["accepted_count"] == 5
    assert data["priority_counts"]["CRITICAL"] == 2
    assert data["priority_counts"]["NORMAL"] == 1
    assert data["priority_counts"]["BEST_EFFORT"] == 2


@pytest.mark.asyncio
async def test_enqueue_handler_forwarding(app):
    forwarded = []

    async def mock_enqueue(event: Event, priority: Priority):
        forwarded.append((event.event_id, priority))

    set_enqueue_handler(mock_enqueue)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        await ac.post("/events", json={"event_id": "fwd-1", "event_type": "PAYMENT"})
        await ac.post("/events", json={"event_id": "fwd-2", "event_type": "INVENTORY_UPDATE"})

    assert len(forwarded) == 2
    assert forwarded[0] == ("fwd-1", Priority.CRITICAL)
    assert forwarded[1] == ("fwd-2", Priority.NORMAL)


@pytest.mark.asyncio
async def test_invalid_event_validation_error(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Missing required event_type field
        response = await ac.post("/events", json={"payload": {"bad": "data"}})
    assert response.status_code == 422

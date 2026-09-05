"""Tests for the event history retrieval endpoints.

Covers:
- GET /events/history  (no filters, event_id, priority, event_type, limit)
- GET /events/{event_id}  (found / 404)
"""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from pipeline.ingestion.api import router
from pipeline.storage.database import DatabaseManager
from pipeline.storage.repository import EventRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    test_app = FastAPI()
    test_app.include_router(router)
    return test_app


@pytest.fixture
async def in_memory_db():
    """Provide an isolated in-memory SQLite DatabaseManager per test."""
    db = DatabaseManager(db_path=":memory:")
    await db.init_db()
    yield db
    await db.close()


@pytest.fixture
async def repo(in_memory_db):
    """Return an EventRepository wired to the in-memory database."""
    return EventRepository(db=in_memory_db)


async def _seed(repo: EventRepository) -> None:
    """Insert a small, deterministic set of processed event records."""
    records = [
        {
            "event_id": "evt-order-001",
            "event_type": "ORDER",
            "priority": "CRITICAL",
            "status": "processed",
            "processing_mode": "adaptive",
            "payload": {"total": 100.0},
            "received_at": 1700000001.0,
            "processed_at": 1700000002.0,
            "latency_ms": 12.5,
        },
        {
            "event_id": "evt-payment-002",
            "event_type": "PAYMENT",
            "priority": "CRITICAL",
            "status": "processed",
            "processing_mode": "adaptive",
            "payload": {"amount": 49.99},
            "received_at": 1700000003.0,
            "processed_at": 1700000004.0,
            "latency_ms": 8.0,
        },
        {
            "event_id": "evt-click-003",
            "event_type": "CLICK",
            "priority": "BEST_EFFORT",
            "status": "processed",
            "processing_mode": "baseline",
            "payload": {"button": "buy"},
            "received_at": 1700000005.0,
            "processed_at": 1700000006.0,
            "latency_ms": 3.1,
        },
        {
            "event_id": "evt-cart-004",
            "event_type": "CART_ADD",
            "priority": "NORMAL",
            "status": "processed",
            "processing_mode": "adaptive",
            "payload": {"item_id": "sku-9"},
            "received_at": 1700000007.0,
            "processed_at": 1700000008.0,
            "latency_ms": 5.0,
        },
        {
            "event_id": "evt-page-005",
            "event_type": "PAGE_VIEW",
            "priority": "BEST_EFFORT",
            "status": "processed",
            "processing_mode": "baseline",
            "payload": {"url": "/home"},
            "received_at": 1700000009.0,
            "processed_at": 1700000010.0,
            "latency_ms": 2.0,
        },
    ]
    await repo.insert_events_batch(records)


# ---------------------------------------------------------------------------
# Helper: build an AsyncClient that uses a patched event_repository
# ---------------------------------------------------------------------------

from unittest.mock import patch


def _client(app, repo: EventRepository) -> AsyncClient:
    """Return an AsyncClient whose requests use *repo* as the event_repository."""
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ---------------------------------------------------------------------------
# Tests: GET /events/history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_history_no_filters(app, repo):
    """All seeded events are returned when no query params are given."""
    await _seed(repo)
    with patch("pipeline.ingestion.api.event_repository", repo):
        async with _client(app, repo) as ac:
            response = await ac.get("/events/history")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["count"] == 5
    assert len(data["events"]) == 5


@pytest.mark.asyncio
async def test_history_newest_first(app, repo):
    """Results are ordered newest processed_at first."""
    await _seed(repo)
    with patch("pipeline.ingestion.api.event_repository", repo):
        async with _client(app, repo) as ac:
            response = await ac.get("/events/history")

    events = response.json()["events"]
    timestamps = [e["processed_at"] for e in events]
    assert timestamps == sorted(timestamps, reverse=True)


@pytest.mark.asyncio
async def test_history_filter_by_event_id(app, repo):
    """Searching by event_id returns exactly one matching event."""
    await _seed(repo)
    with patch("pipeline.ingestion.api.event_repository", repo):
        async with _client(app, repo) as ac:
            response = await ac.get("/events/history", params={"event_id": "evt-order-001"})

    data = response.json()
    assert data["status"] == "success"
    assert data["count"] == 1
    assert data["events"][0]["event_id"] == "evt-order-001"


@pytest.mark.asyncio
async def test_history_filter_by_priority(app, repo):
    """Filtering by priority=CRITICAL returns only CRITICAL events."""
    await _seed(repo)
    with patch("pipeline.ingestion.api.event_repository", repo):
        async with _client(app, repo) as ac:
            response = await ac.get("/events/history", params={"priority": "CRITICAL"})

    data = response.json()
    assert data["count"] == 2
    for evt in data["events"]:
        assert evt["priority"] == "CRITICAL"


@pytest.mark.asyncio
async def test_history_filter_by_event_type(app, repo):
    """Filtering by event_type=CLICK returns only CLICK events."""
    await _seed(repo)
    with patch("pipeline.ingestion.api.event_repository", repo):
        async with _client(app, repo) as ac:
            response = await ac.get("/events/history", params={"event_type": "CLICK"})

    data = response.json()
    assert data["count"] == 1
    assert data["events"][0]["event_type"] == "CLICK"


@pytest.mark.asyncio
async def test_history_filter_by_status(app, repo):
    """Filtering by status=processed returns all seeded events (all are 'processed')."""
    await _seed(repo)
    with patch("pipeline.ingestion.api.event_repository", repo):
        async with _client(app, repo) as ac:
            response = await ac.get("/events/history", params={"status": "processed"})

    data = response.json()
    assert data["count"] == 5


@pytest.mark.asyncio
async def test_history_limit(app, repo):
    """The limit parameter caps the number of returned events."""
    await _seed(repo)
    with patch("pipeline.ingestion.api.event_repository", repo):
        async with _client(app, repo) as ac:
            response = await ac.get("/events/history", params={"limit": 2})

    data = response.json()
    assert data["count"] == 2
    assert len(data["events"]) == 2


@pytest.mark.asyncio
async def test_history_empty_result(app, repo):
    """Filtering by a non-existent event_type returns count=0 and empty list."""
    await _seed(repo)
    with patch("pipeline.ingestion.api.event_repository", repo):
        async with _client(app, repo) as ac:
            response = await ac.get("/events/history", params={"event_type": "DOES_NOT_EXIST"})

    data = response.json()
    assert data["status"] == "success"
    assert data["count"] == 0
    assert data["events"] == []


# ---------------------------------------------------------------------------
# Tests: GET /events/{event_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_single_event_found(app, repo):
    """GET /events/{event_id} returns the event record when it exists."""
    await _seed(repo)
    with patch("pipeline.ingestion.api.event_repository", repo):
        async with _client(app, repo) as ac:
            response = await ac.get("/events/evt-payment-002")

    assert response.status_code == 200
    data = response.json()
    assert data["event_id"] == "evt-payment-002"
    assert data["event_type"] == "PAYMENT"
    assert data["priority"] == "CRITICAL"


@pytest.mark.asyncio
async def test_get_single_event_not_found(app, repo):
    """GET /events/{event_id} returns HTTP 404 for an unknown event ID."""
    with patch("pipeline.ingestion.api.event_repository", repo):
        async with _client(app, repo) as ac:
            response = await ac.get("/events/evt-does-not-exist")

    assert response.status_code == 404
    data = response.json()
    assert "not found" in data["detail"].lower()

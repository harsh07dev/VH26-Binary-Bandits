import pytest
import asyncio
import uuid
import fakeredis
import fakeredis.aioredis
from pipeline.config import config
from pipeline.queues.queue_manager import QueueManager
from contracts.events import Event
from contracts.priorities import Priority

@pytest.fixture(scope="session")
def persistent_fake_server():
    """A single fake Redis server instance simulating a running Redis container."""
    return fakeredis.FakeServer()

@pytest.fixture
def isolated_queue_manager_factory(persistent_fake_server, monkeypatch):
    """Factory to create new QueueManagers simulating an application restart,
    but they all connect to the same persistent Redis server."""
    
    # Mock from_url to connect to the persistent fake server
    import pipeline.queues.redis_queue as rq
    
    def fake_async_from_url(*args, **kwargs):
        return fakeredis.aioredis.FakeRedis(server=persistent_fake_server, decode_responses=True)
        
    def fake_sync_from_url(*args, **kwargs):
        return fakeredis.FakeRedis(server=persistent_fake_server, decode_responses=True)
        
    monkeypatch.setattr(rq.aioredis, "from_url", fake_async_from_url)
    monkeypatch.setattr(rq.syncredis, "from_url", fake_sync_from_url)
    monkeypatch.setattr(config, "queue_backend", "redis")
    monkeypatch.setattr(config, "redis_url", "redis://localhost:6379")
    
    def _create_manager():
        return QueueManager()
        
    return _create_manager

@pytest.mark.asyncio
async def test_application_restart_preserves_events(isolated_queue_manager_factory):
    """
    Scenario:
    1. Start PulseFlow using Redis backend (QM1)
    2. Generate event backlog
    3. Application crashes (QM1 destroyed)
    4. Application restarts (QM2 created)
    5. Verify queued events exist and can be consumed
    """
    # 1. Start Application (Instance 1)
    qm1 = isolated_queue_manager_factory()
    qm1.clear()  # Ensure empty at start
    
    # 2. Generate Backlog
    events = []
    for i in range(10):
        evt = Event(event_id=f"backlog_{i}", event_type="TEST", payload={"data": i}, priority=Priority.NORMAL)
        await qm1.enqueue(evt)
        events.append(evt)
        
    assert qm1.depth(Priority.NORMAL) == 10
    
    # 3. Simulate Application Crash
    del qm1 
    
    # 4. Restart Application (Instance 2)
    qm2 = isolated_queue_manager_factory()
    
    # 5. Verify events still exist
    assert qm2.depth(Priority.NORMAL) == 10
    
    # 6. Consume and verify correctness (IDs and Priority preserved)
    consumed_ids = []
    for i in range(10):
        dequeued = await qm2.get(Priority.NORMAL)
        consumed_ids.append(dequeued.event_id)
        
        # Verify Priority and Payload serialization
        assert dequeued.priority == Priority.NORMAL
        assert dequeued.payload["data"] == i
        
    assert consumed_ids == [f"backlog_{i}" for i in range(10)]
    assert qm2.depth(Priority.NORMAL) == 0

@pytest.mark.asyncio
async def test_redis_connection_failure_behavior(isolated_queue_manager_factory, monkeypatch):
    """
    Scenario: Temporary Redis connection failure.
    If Redis goes down, we should not hide it or fallback yet, but explicitly raise exceptions.
    """
    qm = isolated_queue_manager_factory()
    
    # Simulate a Redis outage by poisoning the queue's redis clients
    import redis.exceptions
    def explode(*args, **kwargs):
        raise redis.exceptions.ConnectionError("Connection refused")
        
    async def async_explode(*args, **kwargs):
        raise redis.exceptions.ConnectionError("Connection refused")

    monkeypatch.setattr(qm.normal_queue.sync_redis, "llen", explode)
    monkeypatch.setattr(qm.normal_queue.async_redis, "rpush", async_explode)
    monkeypatch.setattr(qm.normal_queue.async_redis, "blpop", async_explode)

    # Validate that the error bubbles up clearly and isn't silently swallowed
    with pytest.raises(redis.exceptions.ConnectionError, match="Connection refused"):
        qm.depth(Priority.NORMAL)
        
    with pytest.raises(redis.exceptions.ConnectionError, match="Connection refused"):
        evt = Event(event_id="test", event_type="TEST", payload={})
        await qm.enqueue(evt, priority=Priority.NORMAL)
        
    with pytest.raises(redis.exceptions.ConnectionError, match="Connection refused"):
        await qm.get(Priority.NORMAL)

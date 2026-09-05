import pytest
import asyncio
import redis
import time
from pipeline.config import config
from pipeline.queues.queue_manager import QueueManager
from contracts.events import Event
from contracts.priorities import Priority
from pipeline.queues.redis_queue import RedisLaneQueue
from pipeline.queues.critical_queue import CriticalQueue
from pipeline.queues.normal_queue import NormalQueue
from pipeline.queues.abstract_queue import QueueEmpty

REDIS_URL = "redis://localhost:6379"

def check_redis():
    try:
        r = redis.Redis.from_url(REDIS_URL, socket_timeout=1)
        r.ping()
        return True
    except redis.ConnectionError:
        return False

# Skip the entire module if Redis is not running
pytestmark = pytest.mark.skipif(
    not check_redis(), 
    reason="Real Redis server not available. Start it using docker compose up -d redis"
)

@pytest.fixture(autouse=True)
def clean_redis():
    """Clear Redis database before each test."""
    r = redis.Redis.from_url(REDIS_URL)
    r.flushdb()
    yield
    r.flushdb()

@pytest.fixture
def redis_queue_manager(monkeypatch):
    """Fixture providing a QueueManager forced to use Redis."""
    monkeypatch.setattr(config, "queue_backend", "redis")
    monkeypatch.setattr(config, "redis_url", REDIS_URL)
    return QueueManager()

def test_redis_connection_health():
    """1. Redis connection/health."""
    r = redis.Redis.from_url(REDIS_URL)
    assert r.ping() is True

@pytest.mark.asyncio
async def test_enqueue_dequeue(redis_queue_manager):
    """2. Enqueue/dequeue."""
    event = Event(event_id="test1", event_type="TEST", payload={"msg": "hello"})
    await redis_queue_manager.enqueue(event, priority=Priority.NORMAL)
    
    assert redis_queue_manager.depth(Priority.NORMAL) == 1
    
    dequeued = await redis_queue_manager.get(Priority.NORMAL)
    assert dequeued.event_id == "test1"
    assert redis_queue_manager.depth(Priority.NORMAL) == 0

@pytest.mark.asyncio
async def test_priority_isolation(redis_queue_manager):
    """3, 4, 5. CRITICAL, NORMAL, BEST_EFFORT isolation."""
    # Enqueue one event to each lane
    e_crit = Event(event_id="c1", event_type="TEST", payload={}, priority=Priority.CRITICAL)
    e_norm = Event(event_id="n1", event_type="TEST", payload={}, priority=Priority.NORMAL)
    e_best = Event(event_id="b1", event_type="TEST", payload={}, priority=Priority.BEST_EFFORT)
    
    await redis_queue_manager.enqueue(e_crit)
    await redis_queue_manager.enqueue(e_norm)
    await redis_queue_manager.enqueue(e_best)
    
    # Check isolation by depth
    assert redis_queue_manager.depth(Priority.CRITICAL) == 1
    assert redis_queue_manager.depth(Priority.NORMAL) == 1
    assert redis_queue_manager.depth(Priority.BEST_EFFORT) == 1
    
    # Dequeue specific lanes and ensure others remain untouched
    d_crit = await redis_queue_manager.get(Priority.CRITICAL)
    assert d_crit.event_id == "c1"
    assert redis_queue_manager.depth(Priority.CRITICAL) == 0
    assert redis_queue_manager.depth(Priority.NORMAL) == 1
    
    d_norm = await redis_queue_manager.get(Priority.NORMAL)
    assert d_norm.event_id == "n1"
    
    d_best = await redis_queue_manager.get(Priority.BEST_EFFORT)
    assert d_best.event_id == "b1"

@pytest.mark.asyncio
async def test_fifo_behavior(redis_queue_manager):
    """6. FIFO behavior guarantees."""
    for i in range(5):
        await redis_queue_manager.enqueue(
            Event(event_id=f"seq_{i}", event_type="TEST", payload={}), 
            priority=Priority.NORMAL
        )
    
    for i in range(5):
        event = await redis_queue_manager.get(Priority.NORMAL)
        assert event.event_id == f"seq_{i}"

@pytest.mark.asyncio
async def test_queue_depth(redis_queue_manager):
    """7. Queue depth."""
    assert redis_queue_manager.total_depth() == 0
    await redis_queue_manager.enqueue(Event(event_id="1", event_type="TEST", payload={}), priority=Priority.NORMAL)
    await redis_queue_manager.enqueue(Event(event_id="2", event_type="TEST", payload={}), priority=Priority.NORMAL)
    
    assert redis_queue_manager.depth(Priority.NORMAL) == 2
    assert redis_queue_manager.total_depth() == 2

@pytest.mark.asyncio
async def test_multiple_producers_consumers(redis_queue_manager):
    """8, 9. Multiple producers and consumers."""
    num_producers = 3
    events_per_producer = 50
    total_events = num_producers * events_per_producer
    
    async def producer(p_id):
        for i in range(events_per_producer):
            event = Event(event_id=f"prod_{p_id}_{i}", event_type="TEST", payload={"worker": p_id})
            await redis_queue_manager.enqueue(event, priority=Priority.NORMAL)
            
    async def consumer():
        consumed = []
        # Non-blocking collect until empty
        while True:
            try:
                event = redis_queue_manager.get_nowait(Priority.NORMAL)
                consumed.append(event)
            except QueueEmpty:
                break
        return consumed

    # Run producers concurrently
    await asyncio.gather(*(producer(i) for i in range(num_producers)))
    
    assert redis_queue_manager.depth(Priority.NORMAL) == total_events
    
    # Run consumers concurrently
    num_consumers = 2
    results = await asyncio.gather(*(consumer() for _ in range(num_consumers)))
    
    total_consumed = sum(len(res) for res in results)
    assert total_consumed == total_events
    assert redis_queue_manager.depth(Priority.NORMAL) == 0

@pytest.mark.asyncio
async def test_event_serialization_priority(redis_queue_manager):
    """10, 11. Event serialization/deserialization and priority preservation."""
    payload = {"nested": {"key": "value", "list": [1, 2, 3]}}
    event = Event(event_id="e1", event_type="COMPLEX", payload=payload, priority=Priority.BEST_EFFORT)
    
    await redis_queue_manager.enqueue(event)
    dequeued = await redis_queue_manager.get(Priority.BEST_EFFORT)
    
    assert dequeued.event_id == "e1"
    assert dequeued.event_type == "COMPLEX"
    assert dequeued.priority == Priority.BEST_EFFORT
    assert dequeued.payload == payload

def test_backend_selection_and_switching(monkeypatch):
    """12, 13, 14. Backend selection through config and switching."""
    
    # Switch to asyncio
    monkeypatch.setattr(config, "queue_backend", "asyncio")
    qm_asyncio = QueueManager()
    assert isinstance(qm_asyncio.critical_queue, CriticalQueue)
    assert isinstance(qm_asyncio.normal_queue, NormalQueue)
    assert not isinstance(qm_asyncio.critical_queue, RedisLaneQueue)
    
    # Switch to redis
    monkeypatch.setattr(config, "queue_backend", "redis")
    qm_redis = QueueManager()
    assert isinstance(qm_redis.critical_queue, RedisLaneQueue)
    assert isinstance(qm_redis.normal_queue, RedisLaneQueue)
    
    # Switch back to asyncio (asyncio backend still works unchanged)
    monkeypatch.setattr(config, "queue_backend", "asyncio")
    qm_asyncio_2 = QueueManager()
    assert isinstance(qm_asyncio_2.critical_queue, CriticalQueue)

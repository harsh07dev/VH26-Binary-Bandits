import pytest
import asyncio
import fakeredis
import fakeredis.aioredis
from contracts.events import Event
from contracts.priorities import Priority
from pipeline.queues.abstract_queue import QueueEmpty, QueueFull
from pipeline.queues.redis_queue import RedisLaneQueue

@pytest.fixture(scope="session")
def fake_redis_server():
    return fakeredis.FakeServer()

@pytest.fixture
def fake_sync_redis(fake_redis_server):
    return fakeredis.FakeRedis(server=fake_redis_server, decode_responses=True)

@pytest.fixture
def fake_async_redis(fake_redis_server):
    return fakeredis.aioredis.FakeRedis(server=fake_redis_server, decode_responses=True)

@pytest.fixture
def redis_queue(fake_sync_redis, fake_async_redis, monkeypatch):
    # Monkeypatch to avoid network calls in __init__
    import pipeline.queues.redis_queue as rq
    monkeypatch.setattr(rq.aioredis, "from_url", lambda *args, **kwargs: fake_async_redis)
    monkeypatch.setattr(rq.syncredis, "from_url", lambda *args, **kwargs: fake_sync_redis)
    
    # Flush DB to isolate tests
    fake_sync_redis.flushall()
    
    queue = RedisLaneQueue(priority=Priority.NORMAL, redis_url="fake://localhost", capacity=3)
    return queue

@pytest.mark.asyncio
async def test_enqueue_dequeue(redis_queue):
    event = Event(event_id="1", event_type="TEST", payload={})
    await redis_queue.enqueue(event)
    assert redis_queue.depth() == 1
    
    dequeued = await redis_queue.dequeue()
    assert dequeued.event_id == "1"
    assert dequeued.priority == Priority.NORMAL
    assert redis_queue.depth() == 0
    assert redis_queue.total_enqueued == 1
    assert redis_queue.total_dequeued == 1

@pytest.mark.asyncio
async def test_enqueue_capacity_limit(redis_queue):
    for i in range(3):
        await redis_queue.enqueue(Event(event_id=str(i), event_type="TEST", payload={}))
    
    assert redis_queue.depth() == 3
    assert redis_queue.is_full() is True
    
    with pytest.raises(QueueFull):
        await redis_queue.enqueue(Event(event_id="4", event_type="TEST", payload={}))

@pytest.mark.asyncio
async def test_enqueue_nowait_capacity_limit(redis_queue):
    for i in range(3):
        redis_queue.enqueue_nowait(Event(event_id=str(i), event_type="TEST", payload={}))
    
    with pytest.raises(QueueFull):
        redis_queue.enqueue_nowait(Event(event_id="4", event_type="TEST", payload={}))

@pytest.mark.asyncio
async def test_dequeue_nowait(redis_queue):
    with pytest.raises(QueueEmpty):
        redis_queue.dequeue_nowait()
        
    await redis_queue.enqueue(Event(event_id="1", event_type="TEST", payload={}))
    dequeued = redis_queue.dequeue_nowait()
    assert dequeued.event_id == "1"

@pytest.mark.asyncio
async def test_peek(redis_queue):
    assert redis_queue.peek() is None
    await redis_queue.enqueue(Event(event_id="1", event_type="TEST", payload={}))
    await redis_queue.enqueue(Event(event_id="2", event_type="TEST", payload={}))
    
    peeked = redis_queue.peek()
    assert peeked is not None
    assert peeked.event_id == "1"
    
    # Peek should not remove
    assert redis_queue.depth() == 2

@pytest.mark.asyncio
async def test_clear(redis_queue):
    await redis_queue.enqueue(Event(event_id="1", event_type="TEST", payload={}))
    await redis_queue.enqueue(Event(event_id="2", event_type="TEST", payload={}))
    
    count = redis_queue.clear()
    assert count == 2
    assert redis_queue.depth() == 0
    assert redis_queue.is_empty() is True

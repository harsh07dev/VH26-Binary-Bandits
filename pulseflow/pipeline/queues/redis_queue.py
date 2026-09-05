"""PulseFlow pipeline: Redis Queue Backend.

Implements the AbstractLaneQueue interface using Redis as the backend.
Maintains priority isolation by using a separate Redis key per lane.
"""

import json
from typing import Optional
import redis.asyncio as aioredis
import redis as syncredis
from contracts.priorities import Priority
from contracts.events import Event
from pipeline.queues.abstract_queue import AbstractLaneQueue, QueueEmpty, QueueFull


class RedisLaneQueue(AbstractLaneQueue):
    """Redis-backed queue for an individual priority lane."""

    def __init__(self, priority: Priority, redis_url: str, capacity: Optional[int] = None) -> None:
        super().__init__(priority=priority, capacity=capacity)
        
        # We need both async and sync clients. Async for enqueue/dequeue in the hot path.
        # Sync for inspection methods (depth, peek) to satisfy the synchronous AbstractLaneQueue contract.
        self.async_redis = aioredis.from_url(redis_url, decode_responses=True)
        self.sync_redis = syncredis.from_url(redis_url, decode_responses=True)
        
        self.queue_key = f"pulseflow:queue:{self.priority.value.lower()}"
        
        # Telemetry counters (in-memory for this instance)
        self._enqueued_count: int = 0
        self._dequeued_count: int = 0

    async def enqueue(self, event: Event) -> None:
        """Asynchronously enqueue an event."""
        if event.priority is None:
            event.priority = self.priority
        
        if self.capacity is not None:
            current_len = await self.async_redis.llen(self.queue_key)
            if current_len >= self.capacity:
                raise QueueFull("Redis queue is at capacity")

        event_data = event.model_dump_json() if hasattr(event, "model_dump_json") else json.dumps(event.dict())
        await self.async_redis.rpush(self.queue_key, event_data)
        self._enqueued_count += 1

    async def dequeue(self) -> Event:
        """Asynchronously dequeue an event. Blocks until an event is available."""
        result = await self.async_redis.blpop(self.queue_key, timeout=0)
        if result is None:
            raise QueueEmpty("Redis queue is empty and BLPOP failed")
            
        _, event_data = result
        event_dict = json.loads(event_data)
        event = Event(**event_dict)
        self._dequeued_count += 1
        return event

    def enqueue_nowait(self, event: Event) -> None:
        """Synchronously enqueue an event. Raises QueueFull if bounded and full."""
        if event.priority is None:
            event.priority = self.priority
            
        if self.capacity is not None:
            current_len = self.sync_redis.llen(self.queue_key)
            if current_len >= self.capacity:
                raise QueueFull("Redis queue is at capacity")

        event_data = event.model_dump_json() if hasattr(event, "model_dump_json") else json.dumps(event.dict())
        self.sync_redis.rpush(self.queue_key, event_data)
        self._enqueued_count += 1

    def dequeue_nowait(self) -> Event:
        """Synchronously dequeue an event. Raises QueueEmpty if empty."""
        result = self.sync_redis.lpop(self.queue_key)
        if result is None:
            raise QueueEmpty("Redis queue is empty")
            
        event_dict = json.loads(result)
        event = Event(**event_dict)
        self._dequeued_count += 1
        return event

    def peek(self) -> Optional[Event]:
        """Non-destructively peek at the head of the queue using LRANGE."""
        items = self.sync_redis.lrange(self.queue_key, 0, 0)
        if not items:
            return None
            
        event_dict = json.loads(items[0])
        return Event(**event_dict)

    def depth(self) -> int:
        """Current number of items in the Redis queue."""
        return self.sync_redis.llen(self.queue_key)

    def is_empty(self) -> bool:
        return self.depth() == 0
        
    def is_full(self) -> bool:
        if self.capacity is None:
            return False
        return self.depth() >= self.capacity

    def task_done(self) -> None:
        """Redis BLPOP is atomic; no explicit ACK/task_done is required."""
        pass

    def clear(self) -> int:
        """Drain all elements from the queue and return the number drained."""
        count = self.depth()
        if count > 0:
            self.sync_redis.delete(self.queue_key)
        return count

    @property
    def total_enqueued(self) -> int:
        return self._enqueued_count

    @property
    def total_dequeued(self) -> int:
        return self._dequeued_count

    def __repr__(self) -> str:
        return f"<RedisLaneQueue(priority={self.priority.value}, key={self.queue_key})>"

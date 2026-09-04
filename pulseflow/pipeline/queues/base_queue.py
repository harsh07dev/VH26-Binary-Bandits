"""PulseFlow pipeline: Base Queue.

Defines the core asynchronous queue abstraction shared across all priority lanes.
Wraps asyncio.Queue with metric counters, draining support, and Priority awareness.
"""

import asyncio
from typing import Optional
from contracts.priorities import Priority
from contracts.events import Event


class LaneQueue:
    """Asynchronous in-memory queue for an individual priority lane."""

    def __init__(self, priority: Priority, maxsize: int = 0) -> None:
        self.priority = priority
        self.maxsize = maxsize
        self._queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=maxsize)
        self._enqueued_count: int = 0
        self._dequeued_count: int = 0

    async def enqueue(self, event: Event) -> None:
        """Enqueue an event asynchronously."""
        if event.priority is None:
            event.priority = self.priority
        await self._queue.put(event)
        self._enqueued_count += 1

    def enqueue_nowait(self, event: Event) -> None:
        """Enqueue an event immediately without awaiting.
        
        Raises asyncio.QueueFull if the queue has maxsize and is full.
        """
        if event.priority is None:
            event.priority = self.priority
        self._queue.put_nowait(event)
        self._enqueued_count += 1

    # Aliases matching asyncio.Queue naming
    async def put(self, event: Event) -> None:
        """Alias for enqueue."""
        await self.enqueue(event)

    def put_nowait(self, event: Event) -> None:
        """Alias for enqueue_nowait."""
        self.enqueue_nowait(event)

    async def dequeue(self) -> Event:
        """Dequeue the next event asynchronously."""
        event = await self._queue.get()
        self._dequeued_count += 1
        return event

    def dequeue_nowait(self) -> Event:
        """Dequeue the next event immediately without awaiting.
        
        Raises asyncio.QueueEmpty if empty.
        """
        event = self._queue.get_nowait()
        self._dequeued_count += 1
        return event

    # Aliases matching asyncio.Queue naming
    async def get(self) -> Event:
        """Alias for dequeue."""
        return await self.dequeue()

    def get_nowait(self) -> Event:
        """Alias for dequeue_nowait."""
        return self.dequeue_nowait()

    def depth(self) -> int:
        """Return the current number of events buffered in this lane."""
        return self._queue.qsize()

    def qsize(self) -> int:
        """Alias for depth."""
        return self._queue.qsize()

    def is_empty(self) -> bool:
        """Return True if the queue is empty."""
        return self._queue.empty()

    def empty(self) -> bool:
        """Alias for is_empty."""
        return self._queue.empty()

    def is_full(self) -> bool:
        """Return True if the queue is at capacity."""
        return self._queue.full()

    def full(self) -> bool:
        """Alias for is_full."""
        return self._queue.full()

    def task_done(self) -> None:
        """Indicate that a formerly enqueued task is complete."""
        self._queue.task_done()

    def clear(self) -> int:
        """Drain and discard all currently queued events. Returns count of removed events."""
        drained = 0
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
                drained += 1
            except (asyncio.QueueEmpty, ValueError):
                break
        return drained

    @property
    def total_enqueued(self) -> int:
        """Lifetime count of events enqueued into this lane."""
        return self._enqueued_count

    @property
    def total_dequeued(self) -> int:
        """Lifetime count of events dequeued from this lane."""
        return self._dequeued_count

    def __len__(self) -> int:
        return self.depth()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(priority={self.priority.value}, depth={self.depth()})>"

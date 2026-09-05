"""PulseFlow pipeline: Base Queue.

Defines the core asynchronous queue abstraction shared across all priority lanes.
Wraps asyncio.Queue with metric counters, draining support, and Priority awareness.
"""

import asyncio
from typing import Optional
from contracts.priorities import Priority
from contracts.events import Event
from pipeline.queues.abstract_queue import AbstractLaneQueue, QueueEmpty, QueueFull


class LaneQueue(AbstractLaneQueue):
    """Asynchronous in-memory queue for an individual priority lane."""

    def __init__(self, priority: Priority, maxsize: int = 0, capacity: Optional[int] = None) -> None:
        super().__init__(priority=priority, capacity=capacity)
        self.maxsize = maxsize
        # Explicit finite capacity (for pressure calculations). If 0 or None, treated as unbounded (None)
        if capacity is not None:
            self.capacity: Optional[int] = capacity if capacity > 0 else None
        else:
            self.capacity: Optional[int] = maxsize if maxsize > 0 else None

        self._queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=maxsize)
        self._enqueued_count: int = 0
        self._dequeued_count: int = 0

    @property
    def is_unbounded(self) -> bool:
        """True if the queue has no finite upper capacity limit."""
        return self.capacity is None

    @property
    def queue(self) -> asyncio.Queue[Event]:
        """Return the underlying asyncio.Queue, resetting if bound to a closed or foreign event loop."""
        try:
            current_loop = asyncio.get_running_loop()
            q_loop = getattr(self._queue, "_loop", None)
            if q_loop is not None and (q_loop.is_closed() or q_loop is not current_loop):
                self._queue = asyncio.Queue(maxsize=self.maxsize)
        except RuntimeError:
            pass
        return self._queue

    async def enqueue(self, event: Event) -> None:
        """Enqueue an event asynchronously."""
        if event.priority is None:
            event.priority = self.priority
        await self.queue.put(event)
        self._enqueued_count += 1

    def enqueue_nowait(self, event: Event) -> None:
        """Enqueue an event immediately without awaiting.
        
        Raises QueueFull if the queue has maxsize and is full.
        """
        if event.priority is None:
            event.priority = self.priority
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull as e:
            raise QueueFull("Queue is at capacity") from e
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
        event = await self.queue.get()
        self._dequeued_count += 1
        return event

    def dequeue_nowait(self) -> Event:
        """Dequeue the next event immediately without awaiting.
        
        Raises QueueEmpty if empty.
        """
        try:
            event = self.queue.get_nowait()
        except asyncio.QueueEmpty as e:
            raise QueueEmpty("Queue is empty") from e
        self._dequeued_count += 1
        return event

    def peek(self) -> Optional[Event]:
        """Inspect the head event without removing it, or None if the queue is empty."""
        try:
            q = self.queue
            internal_deque = getattr(q, "_queue", None)
            if internal_deque and len(internal_deque) > 0:
                return internal_deque[0]
        except (AttributeError, IndexError):
            pass
        return None

    # Aliases matching asyncio.Queue naming
    async def get(self) -> Event:
        """Alias for dequeue."""
        return await self.dequeue()

    def get_nowait(self) -> Event:
        """Alias for dequeue_nowait."""
        return self.dequeue_nowait()

    def depth(self) -> int:
        """Return the current number of events buffered in this lane."""
        return self.queue.qsize()

    def qsize(self) -> int:
        """Alias for depth."""
        return self.queue.qsize()

    def is_empty(self) -> bool:
        """Return True if the queue is empty."""
        return self.queue.empty()

    def empty(self) -> bool:
        """Alias for is_empty."""
        return self.queue.empty()

    def is_full(self) -> bool:
        """Return True if the queue is at capacity."""
        return self.queue.full()

    def full(self) -> bool:
        """Alias for is_full."""
        return self.queue.full()

    def task_done(self) -> None:
        """Indicate that a formerly enqueued task is complete."""
        self.queue.task_done()

    def clear(self) -> int:
        """Drain and discard all currently queued events. Returns count of removed events."""
        drained = 0
        try:
            q = self.queue
            while not q.empty():
                try:
                    q.get_nowait()
                    q.task_done()
                    drained += 1
                except (asyncio.QueueEmpty, ValueError):
                    break
        except (RuntimeError, Exception):
            pass
        self._queue = asyncio.Queue(maxsize=self.maxsize)
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

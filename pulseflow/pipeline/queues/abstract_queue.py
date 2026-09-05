"""PulseFlow pipeline: Abstract Queue Interface.

Defines the backend-agnostic queue contract required by PulseFlow.
This allows switching between asyncio.Queue, Redis, or other backends
without changing business logic.
"""

import abc
from typing import Optional
from contracts.events import Event
from contracts.priorities import Priority


class QueueEmpty(Exception):
    """Backend-agnostic exception raised when dequeue_nowait is called on an empty queue."""
    pass


class QueueFull(Exception):
    """Backend-agnostic exception raised when enqueue_nowait is called on a full bounded queue."""
    pass


class AbstractLaneQueue(abc.ABC):
    """Abstract interface for a single priority lane queue."""

    def __init__(self, priority: Priority, capacity: Optional[int] = None) -> None:
        self.priority = priority
        self.capacity = capacity

    # --- Core async operations ---

    @abc.abstractmethod
    async def enqueue(self, event: Event) -> None:
        """Asynchronously enqueue an event. Blocks if bounded and full."""
        pass

    @abc.abstractmethod
    async def dequeue(self) -> Event:
        """Asynchronously dequeue an event. Blocks if empty."""
        pass

    # --- Synchronous / non-blocking operations ---

    @abc.abstractmethod
    def enqueue_nowait(self, event: Event) -> None:
        """Synchronously enqueue an event. Raises QueueFull if bounded and full."""
        pass

    @abc.abstractmethod
    def dequeue_nowait(self) -> Event:
        """Synchronously dequeue an event. Raises QueueEmpty if empty."""
        pass

    @abc.abstractmethod
    def peek(self) -> Optional[Event]:
        """Non-destructively peek at the head of the queue. Returns None if empty."""
        pass

    # --- Inspection ---

    @abc.abstractmethod
    def depth(self) -> int:
        """Current number of items in the queue."""
        pass

    @abc.abstractmethod
    def is_empty(self) -> bool:
        """Return True if the queue is currently empty."""
        pass

    @abc.abstractmethod
    def is_full(self) -> bool:
        """Return True if the queue is bounded and currently full."""
        pass

    # --- Lifecycle & Maintenance ---

    @abc.abstractmethod
    def task_done(self) -> None:
        """Mark a previously dequeued task as completed (for backends that support it)."""
        pass

    @abc.abstractmethod
    def clear(self) -> int:
        """Drain all elements from the queue and return the number drained."""
        pass

    # --- Telemetry ---

    @property
    @abc.abstractmethod
    def total_enqueued(self) -> int:
        """Total number of events enqueued over the lifetime of the queue."""
        pass

    @property
    @abc.abstractmethod
    def total_dequeued(self) -> int:
        """Total number of events dequeued over the lifetime of the queue."""
        pass

__all__ = ["AbstractLaneQueue", "QueueEmpty", "QueueFull"]

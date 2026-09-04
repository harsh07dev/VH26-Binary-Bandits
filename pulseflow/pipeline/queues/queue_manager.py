"""PulseFlow pipeline: Queue Manager.

Unified management interface for the three logical priority queues.
Provides automatic routing of events by priority, centralized dequeueing,
depth inspection, and queue metrics export for the adaptive engine and dashboard.
"""

from typing import Optional, Union, Dict
from contracts.priorities import Priority
from contracts.events import Event
from contracts.metrics import QueueMetrics
from pipeline.queues.base_queue import LaneQueue
from pipeline.queues.critical_queue import CriticalQueue
from pipeline.queues.normal_queue import NormalQueue
from pipeline.queues.best_effort_queue import BestEffortQueue


class QueueManager:
    """Coordinates and routes events across CRITICAL, NORMAL, and BEST_EFFORT priority queues."""

    def __init__(
        self,
        critical_queue: Optional[CriticalQueue] = None,
        normal_queue: Optional[NormalQueue] = None,
        best_effort_queue: Optional[BestEffortQueue] = None,
    ) -> None:
        self.critical_queue = critical_queue or CriticalQueue()
        self.normal_queue = normal_queue or NormalQueue()
        self.best_effort_queue = best_effort_queue or BestEffortQueue()

        self._queues: Dict[Priority, LaneQueue] = {
            Priority.CRITICAL: self.critical_queue,
            Priority.NORMAL: self.normal_queue,
            Priority.BEST_EFFORT: self.best_effort_queue,
        }

    def _resolve_priority(self, priority: Union[Priority, str]) -> Priority:
        """Resolve a priority enum or string safely."""
        if isinstance(priority, Priority):
            return priority
        return Priority.from_str(priority)

    def get_queue(self, priority: Union[Priority, str]) -> LaneQueue:
        """Retrieve the concrete queue for a given priority lane."""
        p = self._resolve_priority(priority)
        return self._queues[p]

    async def enqueue(self, event: Event, priority: Optional[Union[Priority, str]] = None) -> None:
        """Route and enqueue an event into its designated priority queue.
        
        If priority is explicitly provided, it overrides the event's classified priority.
        Otherwise, the event's classified priority is ensured and used.
        """
        if priority is not None:
            resolved_priority = self._resolve_priority(priority)
            event.priority = resolved_priority
        else:
            resolved_priority = event.ensure_priority()

        queue = self.get_queue(resolved_priority)
        await queue.enqueue(event)

    def enqueue_nowait(self, event: Event, priority: Optional[Union[Priority, str]] = None) -> None:
        """Synchronously route and enqueue an event without awaiting."""
        if priority is not None:
            resolved_priority = self._resolve_priority(priority)
            event.priority = resolved_priority
        else:
            resolved_priority = event.ensure_priority()

        queue = self.get_queue(resolved_priority)
        queue.enqueue_nowait(event)

    async def get(self, priority: Union[Priority, str]) -> Event:
        """Dequeue the next event from the specified priority lane."""
        queue = self.get_queue(priority)
        return await queue.dequeue()

    def get_nowait(self, priority: Union[Priority, str]) -> Event:
        """Dequeue the next event immediately from the specified priority lane."""
        queue = self.get_queue(priority)
        return queue.dequeue_nowait()

    def depth(self, priority: Union[Priority, str]) -> int:
        """Return the current depth (number of waiting events) for a priority lane."""
        queue = self.get_queue(priority)
        return queue.depth()

    def depths(self) -> Dict[str, int]:
        """Return a mapping of all priority lane names to their current depths."""
        return {
            Priority.CRITICAL.value: self.critical_queue.depth(),
            Priority.NORMAL.value: self.normal_queue.depth(),
            Priority.BEST_EFFORT.value: self.best_effort_queue.depth(),
        }

    def total_depth(self) -> int:
        """Return the aggregate depth across all three priority queues."""
        return (
            self.critical_queue.depth()
            + self.normal_queue.depth()
            + self.best_effort_queue.depth()
        )

    def queue_metrics(self) -> QueueMetrics:
        """Generate a snapshot of queue depths conforming to the shared QueueMetrics contract."""
        return QueueMetrics(
            critical=self.critical_queue.depth(),
            normal=self.normal_queue.depth(),
            best_effort=self.best_effort_queue.depth(),
        )

    def is_empty(self) -> bool:
        """Return True if all three queues are currently empty."""
        return self.total_depth() == 0

    def clear(self) -> Dict[str, int]:
        """Drain and discard all items in all queues. Returns counts of drained items."""
        return {
            Priority.CRITICAL.value: self.critical_queue.clear(),
            Priority.NORMAL.value: self.normal_queue.clear(),
            Priority.BEST_EFFORT.value: self.best_effort_queue.clear(),
        }

    def __repr__(self) -> str:
        return (
            f"<QueueManager "
            f"critical={self.critical_queue.depth()} "
            f"normal={self.normal_queue.depth()} "
            f"best_effort={self.best_effort_queue.depth()} "
            f"total={self.total_depth()}>"
        )


# Default singleton instance used across the pipeline
queue_manager = QueueManager()

__all__ = ["QueueManager", "queue_manager"]

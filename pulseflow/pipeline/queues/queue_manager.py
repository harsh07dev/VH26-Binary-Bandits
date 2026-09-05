"""PulseFlow pipeline: Queue Manager.

Unified management interface for the three logical priority queues.
Provides automatic routing of events by priority, centralized dequeueing,
depth inspection, and queue metrics export for the adaptive engine and dashboard.
"""

from typing import Optional, Union, Dict, List
import time
from contracts.priorities import Priority
from contracts.events import Event
from contracts.metrics import QueueMetrics
from pipeline.queues.base_queue import LaneQueue
from pipeline.queues.critical_queue import CriticalQueue
from pipeline.queues.normal_queue import NormalQueue
from pipeline.queues.best_effort_queue import BestEffortQueue


class QueueGrowthTracker:
    """Tracks queue depth over time to calculate growth rate (dq/dt)."""
    
    def __init__(self, window_size: int = 5):
        self.window_size = window_size
        self._samples: List[tuple[float, int]] = []
        
    def add_sample(self, depth: int) -> None:
        now = time.time()
        self._samples.append((now, depth))
        if len(self._samples) > self.window_size:
            self._samples.pop(0)
            
    def get_growth_rate(self) -> float:
        if len(self._samples) < 2:
            return 0.0
        
        t0, d0 = self._samples[0]
        t1, d1 = self._samples[-1]
        
        dt = t1 - t0
        if dt <= 0:
            return 0.0
            
        return (d1 - d0) / dt


class QueueManager:
    """Coordinates and routes events across CRITICAL, NORMAL, and BEST_EFFORT priority queues."""

    def __init__(
        self,
        critical_queue: Optional[CriticalQueue] = None,
        normal_queue: Optional[NormalQueue] = None,
        best_effort_queue: Optional[BestEffortQueue] = None,
        default_capacity: Optional[int] = None,
    ) -> None:
        self.critical_queue = critical_queue or CriticalQueue(capacity=default_capacity)
        self.normal_queue = normal_queue or NormalQueue(capacity=default_capacity)
        self.best_effort_queue = best_effort_queue or BestEffortQueue(capacity=default_capacity)

        self._queues: Dict[Priority, LaneQueue] = {
            Priority.CRITICAL: self.critical_queue,
            Priority.NORMAL: self.normal_queue,
            Priority.BEST_EFFORT: self.best_effort_queue,
        }
        
        self.growth_tracker = QueueGrowthTracker()
        self.normal_growth_tracker = QueueGrowthTracker()
        self.best_effort_growth_tracker = QueueGrowthTracker()

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

    @property
    def dispatcher(self):
        """Access or instantiate the Dispatcher coordinating Lazy Priority Aging."""
        from pipeline.dispatcher import Dispatcher
        if not hasattr(self, "_dispatcher") or self._dispatcher is None:
            self._dispatcher = Dispatcher(qm=self)
        return self._dispatcher

    async def get_with_aging(
        self,
        priority: Union[Priority, str],
        timeout: Optional[float] = None,
        now: Optional[float] = None,
    ) -> Event:
        """Dequeue the next event with Lazy Priority Aging applied when pulling from NORMAL."""
        p = self._resolve_priority(priority)
        if p == Priority.NORMAL:
            return await self.dispatcher.pop_normal(timeout=timeout, now=now)
        elif p == Priority.CRITICAL:
            return await self.dispatcher.pop_critical(timeout=timeout)
        else:
            return await self.dispatcher.pop_best_effort(timeout=timeout)

    def get_with_aging_nowait(
        self,
        priority: Union[Priority, str],
        now: Optional[float] = None,
    ) -> Event:
        """Dequeue immediately with Lazy Priority Aging applied when pulling from NORMAL."""
        p = self._resolve_priority(priority)
        if p == Priority.NORMAL:
            return self.dispatcher.pop_normal_nowait(now=now)
        elif p == Priority.CRITICAL:
            return self.dispatcher.pop_critical_nowait()
        else:
            return self.dispatcher.pop_best_effort_nowait()

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
        self.growth_tracker.add_sample(self.total_depth())
        self.normal_growth_tracker.add_sample(self.normal_queue.depth())
        self.best_effort_growth_tracker.add_sample(self.best_effort_queue.depth())
        
        return QueueMetrics(
            critical=self.critical_queue.depth(),
            normal=self.normal_queue.depth(),
            best_effort=self.best_effort_queue.depth(),
            total_growth_rate=self.growth_tracker.get_growth_rate(),
            normal_growth_rate=self.normal_growth_tracker.get_growth_rate(),
            best_effort_growth_rate=self.best_effort_growth_tracker.get_growth_rate()
        )

    def capacity(self, priority: Union[Priority, str]) -> Optional[int]:
        """Return the capacity limit of a lane, or None if unbounded."""
        return self.get_queue(priority).capacity

    def capacities(self) -> Dict[str, Optional[int]]:
        """Return capacity limits for all lanes (None if unbounded)."""
        return {
            Priority.CRITICAL.value: self.critical_queue.capacity,
            Priority.NORMAL.value: self.normal_queue.capacity,
            Priority.BEST_EFFORT.value: self.best_effort_queue.capacity,
        }

    def total_capacity(self) -> int:
        """Return aggregate finite capacity across all lanes, or fallback to config."""
        caps = [q.capacity for q in self._queues.values() if q.capacity is not None]
        if caps:
            return sum(caps)
        from pipeline.config import config
        return config.queue_capacity if config.queue_capacity > 0 else 1000

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

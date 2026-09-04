"""PulseFlow pipeline: Critical Queue.

Dedicated queue for CRITICAL priority events (ORDER, PAYMENT).
Critical events must never be shed or degraded; they receive streaming,
dedicated capacity under all system load levels.
"""

from typing import Optional
from contracts.priorities import Priority
from pipeline.queues.base_queue import LaneQueue


class CriticalQueue(LaneQueue):
    """Queue for CRITICAL priority lane events."""

    def __init__(self, maxsize: int = 0, capacity: Optional[int] = None) -> None:
        super().__init__(priority=Priority.CRITICAL, maxsize=maxsize, capacity=capacity)


__all__ = ["CriticalQueue"]

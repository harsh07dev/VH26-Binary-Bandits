"""PulseFlow pipeline: Best-Effort Queue.

Dedicated queue for BEST_EFFORT priority events (CLICK, PAGE_VIEW, LOG).
Best-effort events can be sampled or shed during high system pressure
to protect critical and normal processing capacity.
"""

from typing import Optional
from contracts.priorities import Priority
from pipeline.queues.base_queue import LaneQueue


class BestEffortQueue(LaneQueue):
    """Queue for BEST_EFFORT priority lane events."""

    def __init__(self, maxsize: int = 0, capacity: Optional[int] = None) -> None:
        super().__init__(priority=Priority.BEST_EFFORT, maxsize=maxsize, capacity=capacity)


__all__ = ["BestEffortQueue"]

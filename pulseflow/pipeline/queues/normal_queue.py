"""PulseFlow pipeline: Normal Queue.

Dedicated queue for NORMAL priority events (CART_ADD, INVENTORY_UPDATE).
Normal events are streamed during low load and micro-batched or temporarily
deferred when system pressure rises.
"""

from contracts.priorities import Priority
from pipeline.queues.base_queue import LaneQueue


class NormalQueue(LaneQueue):
    """Queue for NORMAL priority lane events."""

    def __init__(self, maxsize: int = 0) -> None:
        super().__init__(priority=Priority.NORMAL, maxsize=maxsize)


__all__ = ["NormalQueue"]

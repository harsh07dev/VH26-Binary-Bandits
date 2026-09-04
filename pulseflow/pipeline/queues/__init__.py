"""PulseFlow pipeline: Queues package.

Exposes priority queues and QueueManager for the three logical lanes:
- CriticalQueue: ORDER, PAYMENT
- NormalQueue: CART_ADD, INVENTORY_UPDATE
- BestEffortQueue: CLICK, PAGE_VIEW, LOG
- QueueManager: Central routing, dequeueing, and depth inspection
"""

from pipeline.queues.base_queue import LaneQueue
from pipeline.queues.critical_queue import CriticalQueue
from pipeline.queues.normal_queue import NormalQueue
from pipeline.queues.best_effort_queue import BestEffortQueue
from pipeline.queues.queue_manager import QueueManager, queue_manager

__all__ = [
    "LaneQueue",
    "CriticalQueue",
    "NormalQueue",
    "BestEffortQueue",
    "QueueManager",
    "queue_manager",
]

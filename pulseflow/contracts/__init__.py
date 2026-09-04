"""PulseFlow shared contracts package.

Frozen contracts shared across:
- TechPulse (Machine 1 - Harsh)
- PulseFlow Core Pipeline (Machine 2 - Aradhya)
- Adaptive Engine (Shrikar)
- Observability & Benchmarks (Mayur)
"""

from contracts.priorities import (
    Priority,
    EVENT_TYPE_PRIORITY_MAP,
    classify_event_type,
)
from contracts.events import (
    Event,
    EventBatch,
)
from contracts.actions import (
    Action,
)
from contracts.decisions import (
    ProcessingDecision,
    SystemDecision,
    InvalidDecisionError,
    validate_decision_for_event,
)
from contracts.metrics import (
    QueueMetrics,
    WorkerMetrics,
    SystemSnapshot,
)

__all__ = [
    # Priorities
    "Priority",
    "EVENT_TYPE_PRIORITY_MAP",
    "classify_event_type",
    # Events
    "Event",
    "EventBatch",
    # Actions
    "Action",
    # Decisions
    "ProcessingDecision",
    "SystemDecision",
    "InvalidDecisionError",
    "validate_decision_for_event",
    # Metrics
    "QueueMetrics",
    "WorkerMetrics",
    "SystemSnapshot",
]

"""PulseFlow pipeline: Classifier with Dynamic Scoring and Decision Lineage.

Upgrades event classification with a dynamic scoring function:
    Score = (w1 * BasePriority) + (w2 * WaitTime) + (w3 * QueueDepth)

Enriches Event.payload['_audit'] with decision lineage:
    rule_id, score, evaluated_at, features
"""

from __future__ import annotations

import time
from typing import Any, Mapping, Optional, Union

from contracts.events import Event
from contracts.priorities import (
    EVENT_TYPE_PRIORITY_MAP,
    Priority,
    classify_event_type as contracts_classify_event_type,
)

# Standard baseline numeric weights for priority tiers
DEFAULT_BASE_PRIORITY_WEIGHTS: dict[Priority, float] = {
    Priority.CRITICAL: 100.0,
    Priority.NORMAL: 50.0,
    Priority.BEST_EFFORT: 10.0,
}

# Default scoring weights:
# w1: Base priority weight
# w2: Wait time weight (seconds elapsed in queue / pipeline)
# w3: Queue depth weight (backlog pressure)
DEFAULT_W1: float = 1.0
DEFAULT_W2: float = 2.0
DEFAULT_W3: float = 0.5


def calculate_dynamic_score(
    event: Event,
    queue_depth: int = 0,
    current_time: Optional[float] = None,
    w1: float = DEFAULT_W1,
    w2: float = DEFAULT_W2,
    w3: float = DEFAULT_W3,
    base_priority_weights: Optional[Mapping[Priority, float]] = None,
) -> float:
    """Compute the dynamic priority score using the formula:
    
        Score = (w1 * BasePriority) + (w2 * WaitTime) + (w3 * QueueDepth)
    """
    weights = base_priority_weights or DEFAULT_BASE_PRIORITY_WEIGHTS
    base_priority = event.ensure_priority()
    base_val = weights.get(base_priority, 10.0)

    now = current_time if current_time is not None else time.time()
    # Reference timestamp: received_at if set, else generation timestamp
    ref_time = event.received_at if event.received_at is not None else event.timestamp
    wait_time = max(0.0, now - ref_time) if ref_time else 0.0

    score = (w1 * base_val) + (w2 * wait_time) + (w3 * max(0, queue_depth))
    return round(float(score), 4)


def classify_with_lineage(
    event: Event,
    queue_depth: int = 0,
    current_time: Optional[float] = None,
    w1: float = DEFAULT_W1,
    w2: float = DEFAULT_W2,
    w3: float = DEFAULT_W3,
    rule_id: Optional[str] = None,
    base_priority_weights: Optional[Mapping[Priority, float]] = None,
) -> tuple[Priority, float, dict[str, Any]]:
    """Classify an event, calculate its dynamic score, and enrich payload['_audit'] with decision lineage.
    
    Hard Invariant:
        CRITICAL events are always strictly protected and never downgraded.
    """
    now = current_time if current_time is not None else time.time()
    base_priority = event.ensure_priority()

    score = calculate_dynamic_score(
        event=event,
        queue_depth=queue_depth,
        current_time=now,
        w1=w1,
        w2=w2,
        w3=w3,
        base_priority_weights=base_priority_weights,
    )

    assigned_rule_id = rule_id or f"rule-dynamic-{base_priority.value.lower()}"
    ref_time = event.received_at if event.received_at is not None else event.timestamp
    wait_time = max(0.0, now - ref_time) if ref_time else 0.0

    features = {
        "event_type": event.event_type,
        "base_priority": base_priority.value,
        "wait_time_sec": round(wait_time, 4),
        "queue_depth": queue_depth,
        "weights": {"w1": w1, "w2": w2, "w3": w3},
    }

    audit_dict = event.attach_audit(
        rule_id=assigned_rule_id,
        score=score,
        evaluated_at=now,
        features=features,
    )

    return base_priority, score, audit_dict


def classify_event_type(event_type: str, default: Priority = Priority.BEST_EFFORT) -> Priority:
    """Classify an event type string to its designated Priority lane."""
    return contracts_classify_event_type(event_type, default=default)


def classify_event(event: Event) -> Priority:
    """Ensure and return the Priority lane for an Event object."""
    return event.ensure_priority()


def classify(target: Union[Event, str]) -> Priority:
    """Universal classification helper accepting either an Event object or an event type string."""
    if isinstance(target, str):
        return classify_event_type(target)
    elif isinstance(target, Event):
        return classify_event(target)
    raise TypeError(f"Expected Event or str, got {type(target).__name__}")


__all__ = [
    "DEFAULT_BASE_PRIORITY_WEIGHTS",
    "DEFAULT_W1",
    "DEFAULT_W2",
    "DEFAULT_W3",
    "EVENT_TYPE_PRIORITY_MAP",
    "Priority",
    "calculate_dynamic_score",
    "classify",
    "classify_event",
    "classify_event_type",
    "classify_with_lineage",
]

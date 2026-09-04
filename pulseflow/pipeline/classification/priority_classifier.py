"""PulseFlow pipeline: Priority Classifier.

Classifies incoming TechPulse events into one of the three logical priority lanes:
- CRITICAL: ORDER, PAYMENT (Zero shedding, streaming processing)
- NORMAL: CART_ADD, INVENTORY_UPDATE (Micro-batched or deferred)
- BEST_EFFORT: CLICK, PAGE_VIEW, LOG (Sampled or shed under pressure)
"""

from typing import Union
from contracts.priorities import (
    Priority,
    EVENT_TYPE_PRIORITY_MAP,
    classify_event_type as contracts_classify_event_type,
)
from contracts.events import Event


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
    "Priority",
    "EVENT_TYPE_PRIORITY_MAP",
    "classify_event_type",
    "classify_event",
    "classify",
]

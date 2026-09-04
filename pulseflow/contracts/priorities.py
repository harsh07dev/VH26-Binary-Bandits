"""PulseFlow contracts: Priorities.

Defines the priority lanes and their mapping from event types.
"""

from enum import Enum
from typing import Optional


class Priority(str, Enum):
    """The three logical priority lanes in PulseFlow."""
    CRITICAL = "CRITICAL"
    NORMAL = "NORMAL"
    BEST_EFFORT = "BEST_EFFORT"

    @classmethod
    def from_str(cls, value: str) -> "Priority":
        """Normalize and parse priority string flexibly (e.g., 'BEST-EFFORT' -> Priority.BEST_EFFORT)."""
        normalized = value.strip().upper().replace("-", "_")
        try:
            return cls[normalized]
        except KeyError:
            raise ValueError(f"Unknown priority: '{value}'. Expected one of {[p.value for p in cls]}")

    def __str__(self) -> str:
        return self.value


# Deterministic mapping from TechPulse event types to PulseFlow priority lanes
EVENT_TYPE_PRIORITY_MAP: dict[str, Priority] = {
    # Critical lane (Strictly protected, zero-shedding, streaming)
    "ORDER": Priority.CRITICAL,
    "PAYMENT": Priority.CRITICAL,

    # Normal lane (Micro-batched or deferred under pressure)
    "CART_ADD": Priority.NORMAL,
    "INVENTORY_UPDATE": Priority.NORMAL,

    # Best-effort lane (Can be sampled or shed under extreme load)
    "CLICK": Priority.BEST_EFFORT,
    "PAGE_VIEW": Priority.BEST_EFFORT,
    "LOG": Priority.BEST_EFFORT,
}


def classify_event_type(event_type: str, default: Priority = Priority.BEST_EFFORT) -> Priority:
    """Classify an event type string into its designated Priority lane."""
    normalized = event_type.strip().upper()
    return EVENT_TYPE_PRIORITY_MAP.get(normalized, default)

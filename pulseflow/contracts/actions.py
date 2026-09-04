"""PulseFlow contracts: Actions.

Defines the processing actions that can be prescribed by the adaptive scheduler.
"""

from enum import Enum


class Action(str, Enum):
    """Processing action for an event or priority lane."""
    # Process immediately as a continuous stream (low latency, CRITICAL default)
    STREAM = "STREAM"

    # Process in micro-batches (high throughput, NORMAL default/pressure mode)
    BATCH = "BATCH"

    # Temporarily defer processing, holding events in the queue
    DEFER = "DEFER"

    # Probabilistically sample a fraction of events and drop the remainder
    SAMPLE = "SAMPLE"

    # Intentionally drop the event (allowed for BEST_EFFORT under extreme load; FORBIDDEN for CRITICAL)
    SHED = "SHED"

    @classmethod
    def from_str(cls, value: str) -> "Action":
        """Normalize and parse action string flexibly."""
        normalized = value.strip().upper()
        try:
            return cls[normalized]
        except KeyError:
            raise ValueError(f"Unknown action: '{value}'. Expected one of {[a.value for a in cls]}")

    def __str__(self) -> str:
        return self.value

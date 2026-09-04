"""PulseFlow contracts: Events.

Defines the structure of incoming TechPulse events and batches.
"""

import time
import uuid
from typing import Any, Optional
from pydantic import BaseModel, Field

from contracts.priorities import Priority, classify_event_type


class Event(BaseModel):
    """Core event contract shared across TechPulse, PulseFlow pipeline, and benchmarks."""
    event_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for the event",
    )
    event_type: str = Field(
        ...,
        description="Event type name (e.g., ORDER, PAYMENT, CART_ADD, CLICK)",
    )
    timestamp: float = Field(
        default_factory=time.time,
        description="Event generation timestamp (epoch seconds)",
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary event payload data",
    )
    priority: Optional[Priority] = Field(
        default=None,
        description="Assigned priority lane (CRITICAL, NORMAL, BEST_EFFORT)",
    )
    received_at: Optional[float] = Field(
        default=None,
        description="Pipeline ingestion timestamp (epoch seconds)",
    )

    def ensure_priority(self) -> Priority:
        """Ensure priority is assigned based on event_type if not already set."""
        if self.priority is None:
            self.priority = classify_event_type(self.event_type)
        return self.priority


class EventBatch(BaseModel):
    """Batch of events for bulk ingestion."""
    events: list[Event] = Field(
        default_factory=list,
        description="List of events in the batch",
    )

    def __len__(self) -> int:
        return len(self.events)

    def __iter__(self):
        return iter(self.events)

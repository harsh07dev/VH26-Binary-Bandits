"""PulseFlow adaptive: Event Classifier.

Classifies incoming events into Priority lanes and provides detailed
classification reasons for the intelligence layer.
"""

from typing import Union
from pydantic import BaseModel, Field

from contracts.events import Event
from contracts.priorities import Priority, EVENT_TYPE_PRIORITY_MAP


class ClassificationResult(BaseModel):
    """Structured result of an adaptive classification."""
    event_id: str = Field(..., description="The ID of the classified event")
    event_type: str = Field(..., description="The type of the event")
    assigned_priority: Priority = Field(..., description="The assigned priority lane")
    reason: str = Field(..., description="Explanation of why this priority was assigned")


class AdaptiveClassifier:
    """Intelligent event classifier for PulseFlow adaptive layer."""

    @classmethod
    def classify(cls, event: Event) -> ClassificationResult:
        """Classify an event and return a detailed ClassificationResult."""
        
        # We rely on the core contracts for the deterministic classification
        normalized_type = event.event_type.strip().upper()
        
        # Check if it's explicitly mapped
        if normalized_type in EVENT_TYPE_PRIORITY_MAP:
            priority = EVENT_TYPE_PRIORITY_MAP[normalized_type]
            reason = f"Explicitly mapped event type '{normalized_type}' to {priority.value}"
        else:
            # Fallback to BEST_EFFORT
            priority = Priority.BEST_EFFORT
            reason = f"Unmapped event type '{normalized_type}' defaults to {priority.value}"
            
        # Ensure the event itself also gets updated
        event.priority = priority
            
        return ClassificationResult(
            event_id=event.event_id,
            event_type=event.event_type,
            assigned_priority=priority,
            reason=reason
        )

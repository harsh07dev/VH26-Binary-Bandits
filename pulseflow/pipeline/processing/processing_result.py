"""PulseFlow pipeline: Processing Result model.

Defines the output structure of event processing operations.
"""

import time
from pydantic import BaseModel, Field
from contracts.priorities import Priority


class ProcessingResult(BaseModel):
    """Result of processing a single event through the pipeline."""
    event_id: str = Field(..., description="Unique event ID")
    event_type: str = Field(..., description="Event type name")
    priority: Priority = Field(..., description="Priority lane")
    processing_mode: str = Field(..., description="Execution mode: STREAM, BATCH, etc.")
    status: str = Field(default="processed", description="Processing status")
    latency_ms: float = Field(default=0.0, description="Latency from ingestion to persistence in ms")
    processed_at: float = Field(default_factory=time.time, description="Timestamp when processing completed")


__all__ = ["ProcessingResult"]

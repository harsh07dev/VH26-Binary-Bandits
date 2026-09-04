"""PulseFlow pipeline: Ingestion Models.

Defines the HTTP request/response schemas for the FastAPI ingestion service.
"""

import time
from typing import Optional
from pydantic import BaseModel, Field

from contracts.priorities import Priority
from contracts.events import Event


class IngestResponse(BaseModel):
    """Response returned after ingesting a single event."""
    status: str = Field(default="accepted", description="Status string: 'accepted' or 'rejected'")
    event_id: str = Field(..., description="The unique ID of the ingested event")
    priority: Optional[Priority] = Field(default=None, description="The classified priority lane")
    received_at: float = Field(default_factory=time.time, description="Timestamp when event was accepted")


class BatchIngestRequest(BaseModel):
    """Request schema for batch event ingestion."""
    events: list[Event] = Field(..., description="List of events to ingest")


class BatchIngestResponse(BaseModel):
    """Response returned after ingesting a batch of events."""
    status: str = Field(default="accepted", description="Status string: 'accepted' or 'partial'")
    total_received: int = Field(..., description="Total number of events submitted in the batch")
    accepted_count: int = Field(..., description="Number of events successfully accepted")
    rejected_count: int = Field(default=0, description="Number of events rejected due to errors")
    priority_counts: dict[str, int] = Field(
        default_factory=dict,
        description="Breakdown of accepted events per priority lane",
    )
    received_at: float = Field(default_factory=time.time, description="Timestamp of batch receipt")


class HealthResponse(BaseModel):
    """Response returned by GET /health."""
    status: str = Field(default="healthy", description="Service health indicator")
    service: str = Field(default="pulseflow-ingestion", description="Service name")
    timestamp: float = Field(default_factory=time.time, description="Current server epoch time")

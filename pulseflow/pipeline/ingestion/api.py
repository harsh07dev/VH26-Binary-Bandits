"""PulseFlow pipeline: Ingestion API.

FastAPI endpoints receiving events from TechPulse (Machine 1).
Provides single and batch ingestion with validation and priority stamping.
"""

import time
from typing import Callable, Optional, Awaitable, Union
from fastapi import APIRouter, HTTPException, status

from contracts.events import Event, EventBatch
from contracts.priorities import Priority, classify_event_type
from pipeline.ingestion.models import (
    IngestResponse,
    BatchIngestRequest,
    BatchIngestResponse,
    HealthResponse,
)

router = APIRouter(tags=["Ingestion"])

# Type definition for downstream enqueue handler: (event: Event, priority: Priority) -> Awaitable[None]
EnqueueHandler = Callable[[Event, Priority], Awaitable[None]]

# Active enqueue handler hook (connected to QueueManager when pipeline starts)
_enqueue_handler: Optional[EnqueueHandler] = None


def set_enqueue_handler(handler: Optional[EnqueueHandler]) -> None:
    """Register or replace the downstream queue ingestion handler."""
    global _enqueue_handler
    _enqueue_handler = handler


def get_enqueue_handler() -> Optional[EnqueueHandler]:
    """Retrieve currently registered enqueue handler."""
    return _enqueue_handler


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint for Machine 1 / load balancer / monitoring."""
    return HealthResponse(
        status="healthy",
        service="pulseflow-ingestion",
        timestamp=time.time(),
    )


@router.post("/events", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_single_event(event: Event) -> IngestResponse:
    """Receive, validate, classify, and queue a single TechPulse event.
    
    Returns 202 Accepted with assigned priority and received timestamp.
    """
    now = time.time()
    event.received_at = now
    
    # Classify priority lane if not already assigned
    priority = event.ensure_priority()

    # Forward to queue manager if registered
    if _enqueue_handler is not None:
        try:
            await _enqueue_handler(event, priority)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Queue ingestion failed: {str(exc)}",
            )

    return IngestResponse(
        status="accepted",
        event_id=event.event_id,
        priority=priority,
        received_at=now,
    )


@router.post("/events/batch", response_model=BatchIngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_batch_events(payload: Union[BatchIngestRequest, list[Event]]) -> BatchIngestResponse:
    """Receive, validate, classify, and queue a batch of TechPulse events.
    
    Supports both a JSON object with {'events': [...]} and a direct JSON array [...].
    Returns 202 Accepted with summary counts per priority lane.
    """
    events_list = payload.events if isinstance(payload, BatchIngestRequest) else payload
    now = time.time()
    priority_counts: dict[str, int] = {p.value: 0 for p in Priority}
    accepted_count = 0

    for event in events_list:
        event.received_at = now
        priority = event.ensure_priority()
        priority_counts[priority.value] = priority_counts.get(priority.value, 0) + 1

        if _enqueue_handler is not None:
            try:
                await _enqueue_handler(event, priority)
            except Exception as exc:
                # In high-throughput batching, log and track errors rather than aborting the entire batch
                continue

        accepted_count += 1

    return BatchIngestResponse(
        status="accepted",
        total_received=len(events_list),
        accepted_count=accepted_count,
        rejected_count=len(events_list) - accepted_count,
        priority_counts=priority_counts,
        received_at=now,
    )

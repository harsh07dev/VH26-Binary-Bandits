"""PulseFlow pipeline: Ingestion API.

FastAPI endpoints receiving events from TechPulse (Machine 1).
Provides single and batch ingestion with validation and priority stamping.
"""

import time
from typing import Any, Callable, Dict, List, Optional, Awaitable, Union
from fastapi import APIRouter, HTTPException, Query, status

from contracts.events import Event, EventBatch
from contracts.priorities import Priority, classify_event_type
from pipeline.ingestion.models import (
    IngestResponse,
    BatchIngestRequest,
    BatchIngestResponse,
    HealthResponse,
)

from pipeline.queues.queue_manager import queue_manager, QueueManager
from pipeline.storage.repository import event_repository

router = APIRouter(tags=["Ingestion"])


class BackpressureController:
    """Manages queue memory threshold monitoring and HTTP 429 backpressure state.
    
    Rules:
    - High watermark (>= 95% capacity): trigger backpressure (HTTP 429 to non-critical events).
    - Hard Invariant: CRITICAL events (ORDER, PAYMENT) are NEVER throttled and remain unblocked.
    - Low watermark (< 80% capacity): automatically clear backpressure.
    """

    def __init__(
        self,
        qm: Optional[QueueManager] = None,
        high_watermark: float = 0.95,
        low_watermark: float = 0.80,
        total_capacity_override: Optional[int] = None,
    ) -> None:
        self.queue_manager = qm or queue_manager
        self.high_watermark = float(high_watermark)
        self.low_watermark = float(low_watermark)
        self._total_capacity_override = total_capacity_override
        self._depth_override: Optional[int] = None
        self.is_active: bool = False
        self.total_throttled: int = 0

    @property
    def total_capacity(self) -> int:
        if self._total_capacity_override is not None:
            return max(1, self._total_capacity_override)
        return self.queue_manager.total_capacity()

    def set_capacity_override(self, capacity: Optional[int]) -> None:
        self._total_capacity_override = capacity

    @property
    def total_depth(self) -> int:
        if self._depth_override is not None:
            return max(0, self._depth_override)
        return self.queue_manager.total_depth()

    def set_depth_override(self, depth: Optional[int]) -> None:
        self._depth_override = depth

    def update_state(self, current_depth: Optional[int] = None) -> bool:
        """Check total queue depth against watermarks and update backpressure state."""
        depth = current_depth if current_depth is not None else self.total_depth
        cap = self.total_capacity
        ratio = (depth / cap) if cap > 0 else 0.0

        if ratio >= self.high_watermark:
            self.is_active = True
        elif ratio < self.low_watermark:
            self.is_active = False

        return self.is_active

    def should_throttle(self, priority: Priority, current_depth: Optional[int] = None) -> bool:
        """Check if an incoming event with the given priority should be throttled (HTTP 429).
        
        Hard Invariant: CRITICAL events are never throttled under any circumstances.
        """
        active = self.update_state(current_depth=current_depth)
        if not active:
            return False

        if priority == Priority.CRITICAL:
            return False

        self.total_throttled += 1
        return True


# Default singleton controller
backpressure_controller = BackpressureController()

# Type definition for downstream enqueue handler: (event: Event, priority: Priority) -> Awaitable[None]
EnqueueHandler = Callable[[Event, Priority], Awaitable[None]]

# Active enqueue handler hook (defaults to QueueManager's priority routing enqueue)
_enqueue_handler: Optional[EnqueueHandler] = queue_manager.enqueue


def set_enqueue_handler(handler: Optional[EnqueueHandler]) -> None:
    """Register or replace the downstream queue ingestion handler."""
    global _enqueue_handler
    _enqueue_handler = handler


def reset_enqueue_handler() -> None:
    """Reset the enqueue handler back to the default QueueManager routing."""
    global _enqueue_handler
    _enqueue_handler = queue_manager.enqueue


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


@router.get("/metrics/backpressure", tags=["Observability"])
async def get_backpressure_metrics() -> dict[str, Any]:
    """Inspect current queue depth utilization and backpressure status."""
    active = backpressure_controller.update_state()
    depth = queue_manager.total_depth()
    cap = backpressure_controller.total_capacity
    ratio = round(depth / cap, 4) if cap > 0 else 0.0
    return {
        "backpressure_active": active,
        "total_depth": depth,
        "total_capacity": cap,
        "utilization_ratio": ratio,
        "high_watermark": backpressure_controller.high_watermark,
        "low_watermark": backpressure_controller.low_watermark,
        "total_throttled": backpressure_controller.total_throttled,
    }


@router.get("/events/history", tags=["History"])
async def get_event_history(
    event_id: Optional[str] = Query(default=None, description="Filter by exact event ID"),
    event_type: Optional[str] = Query(default=None, description="Filter by event type (e.g. ORDER)"),
    priority: Optional[str] = Query(default=None, description="Filter by priority lane (e.g. CRITICAL)"),
    event_status: Optional[str] = Query(default=None, alias="status", description="Filter by processing status"),
    limit: int = Query(default=50, ge=1, le=1000, description="Maximum number of results to return"),
) -> Dict[str, Any]:
    """Return persisted processed events, newest first.

    All query parameters are optional. Results are capped by *limit* (1–1000).
    """
    events: List[Dict[str, Any]] = await event_repository.get_event_history(
        event_id=event_id,
        event_type=event_type,
        priority=priority,
        status=event_status,
        limit=limit,
    )
    return {
        "status": "success",
        "count": len(events),
        "events": events,
    }


@router.get("/events/{event_id}", tags=["History"])
async def get_single_event(event_id: str) -> Dict[str, Any]:
    """Retrieve a single persisted event by its ID.

    Returns HTTP 404 if no matching event is found in the database.
    """
    event = await event_repository.get_event(event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event '{event_id}' not found.",
        )
    return event


@router.post("/events", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_single_event(event: Event) -> IngestResponse:
    """Receive, validate, classify, and queue a single TechPulse event.
    
    Returns 202 Accepted with assigned priority and received timestamp.
    Under backpressure (>= 95% capacity), returns HTTP 429 to non-critical event producers.
    """
    now = time.time()
    event.received_at = now
    
    # Classify priority lane if not already assigned
    priority = event.ensure_priority()

    # Enforce backpressure on non-critical traffic when depth >= 95% capacity
    if backpressure_controller.should_throttle(priority):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Ingestion backpressure active: queue capacity >= 95%. Non-critical traffic throttled.",
        )

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
    Under backpressure (>= 95% capacity), non-critical events are throttled while
    CRITICAL events remain completely unblocked.
    """
    events_list = payload.events if isinstance(payload, BatchIngestRequest) else payload
    now = time.time()
    priority_counts: dict[str, int] = {p.value: 0 for p in Priority}
    accepted_count = 0

    for event in events_list:
        event.received_at = now
        priority = event.ensure_priority()
        priority_counts[priority.value] = priority_counts.get(priority.value, 0) + 1

        # Check backpressure per event (protects critical events from being dropped)
        if backpressure_controller.should_throttle(priority):
            continue

        if _enqueue_handler is not None:
            try:
                await _enqueue_handler(event, priority)
            except Exception as exc:
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

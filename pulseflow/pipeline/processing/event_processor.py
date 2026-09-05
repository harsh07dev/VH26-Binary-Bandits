"""PulseFlow pipeline: Event Processor.

Executes event transformations, latency calculations, and persists results
via the storage repository.
"""

import time
from typing import List, Optional, Dict
from contracts.priorities import Priority
from contracts.events import Event
from pipeline.processing.processing_result import ProcessingResult
from pipeline.processing.telemetry import ProcessingTelemetryTracker, processing_telemetry
from pipeline.storage.repository import EventRepository, event_repository


class EventProcessor:
    """Processes incoming events individually or in batches and stores them."""

    def __init__(
        self,
        repository: Optional[EventRepository] = None,
        telemetry: Optional[ProcessingTelemetryTracker] = None,
    ) -> None:
        self.repository = repository or event_repository
        self.telemetry = telemetry if telemetry is not None else processing_telemetry

    async def process_single(self, event: Event, mode: str = "STREAM") -> ProcessingResult:
        """Process a single event and persist it to storage."""
        now = time.time()
        start_time = event.received_at if event.received_at is not None else event.timestamp
        latency_ms = max(0.0, (now - start_time) * 1000.0) if start_time else 0.0
        priority = event.ensure_priority()

        await self.repository.insert_event(
            event_id=event.event_id,
            event_type=event.event_type,
            priority=priority.value,
            status="processed",
            processing_mode=mode,
            payload=event.payload,
            received_at=event.received_at,
            processed_at=now,
            latency_ms=latency_ms,
        )

        if self.telemetry is not None:
            self.telemetry.record(latency_ms=latency_ms, priority=priority, now=now)

        return ProcessingResult(
            event_id=event.event_id,
            event_type=event.event_type,
            priority=priority,
            processing_mode=mode,
            status="processed",
            latency_ms=latency_ms,
            processed_at=now,
        )

    async def process_batch(self, events: List[Event], mode: str = "BATCH") -> List[ProcessingResult]:
        """Process a batch of events and persist them in bulk."""
        if not events:
            return []

        now = time.time()
        records = []
        results = []
        lats_by_priority: Dict[Priority, List[float]] = {}

        for event in events:
            start_time = event.received_at if event.received_at is not None else event.timestamp
            latency_ms = max(0.0, (now - start_time) * 1000.0) if start_time else 0.0
            priority = event.ensure_priority()

            records.append(
                {
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "priority": priority.value,
                    "status": "processed",
                    "processing_mode": mode,
                    "payload": event.payload,
                    "received_at": event.received_at,
                    "processed_at": now,
                    "latency_ms": latency_ms,
                }
            )

            results.append(
                ProcessingResult(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    priority=priority,
                    processing_mode=mode,
                    status="processed",
                    latency_ms=latency_ms,
                    processed_at=now,
                )
            )

            lats_by_priority.setdefault(priority, []).append(latency_ms)

        await self.repository.insert_events_batch(records)

        if self.telemetry is not None:
            for p, lats in lats_by_priority.items():
                self.telemetry.record_batch(latencies=lats, priority=p, now=now)

        return results


# Default shared event processor
event_processor = EventProcessor()

__all__ = ["EventProcessor", "event_processor"]

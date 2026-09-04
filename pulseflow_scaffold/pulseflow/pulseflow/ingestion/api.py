from fastapi import APIRouter
from pulseflow.ingestion.models import Event
from pulseflow.classifier.classifier import classify
from pulseflow.queues.priority_queues import queues

router = APIRouter()

@router.post("/events")
async def ingest(event: Event):
    priority = classify(event.event_type)
    await queues.put(priority, event)
    return {
        "accepted": True,
        "event_id": event.event_id,
        "priority": priority,
        "queue_depth": queues.depth(priority),
    }

async def process_batch(events):
    # Phase 2: batch processing + sink write
    return [
        {"status": "processed", "mode": "BATCH", "event_id": event.event_id}
        for event in events
    ]

async def process_stream(event):
    # Phase 2: real processing + sink write
    return {"status": "processed", "mode": "STREAM", "event_id": event.event_id}

def can_shed(priority: str) -> bool:
    # Safety invariant: critical events are never shed.
    return priority == "LOW"

def decide(priority: str, pressure: float) -> str:
    if pressure < 0.4:
        return "STREAM"

    if pressure < 0.7:
        return "STREAM" if priority == "CRITICAL" else "BATCH"

    if pressure < 0.9:
        if priority == "CRITICAL":
            return "STREAM"
        if priority == "MEDIUM":
            return "BATCH"
        return "DEFER"

    if priority == "CRITICAL":
        return "STREAM"
    if priority == "MEDIUM":
        return "DEFER"
    return "SHED"

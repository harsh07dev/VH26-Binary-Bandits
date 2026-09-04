from pulseflow.config import settings

def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))

def calculate_pressure(
    queue_depth: int,
    incoming_rate: float,
    processing_rate: float,
    worker_utilization: float,
    latency_ms: float,
) -> float:
    queue_pressure = clamp(queue_depth / settings.queue_capacity)
    rate_pressure = clamp(
        incoming_rate / max(processing_rate, 1.0) - 1.0
    )
    latency_pressure = clamp(latency_ms / settings.latency_sla_ms)

    return (
        settings.w_queue * queue_pressure
        + settings.w_rate * rate_pressure
        + settings.w_worker * clamp(worker_utilization)
        + settings.w_latency * latency_pressure
    )

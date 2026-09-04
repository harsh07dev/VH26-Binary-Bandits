from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    queue_capacity: int = 10_000
    latency_sla_ms: float = 500.0
    w_queue: float = 0.35
    w_rate: float = 0.30
    w_worker: float = 0.20
    w_latency: float = 0.15

settings = Settings()

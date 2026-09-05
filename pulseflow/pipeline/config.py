"""PulseFlow pipeline: Configuration.

Centralized configuration for Machine 2 pipeline runtime settings.
Loads values from environment variables with production-ready defaults.
"""

import os
from dataclasses import dataclass
from typing import Dict, Optional
from contracts.priorities import Priority


@dataclass
class PipelineConfig:
    """Configuration settings for the PulseFlow processing pipeline."""

    # Server binding
    host: str = "0.0.0.0"
    port: int = 8000

    # Persistence
    db_path: str = "pulseflow.db"

    # Queue Backend (asyncio or redis)
    queue_backend: str = "asyncio"
    redis_url: str = "redis://localhost:6379"

    # Queue sizing: finite capacity (e.g. 1000) for pressure metrics; 0 = unbounded
    queue_capacity: int = 1000

    # Worker allocation defaults
    critical_workers: int = 2
    normal_workers: int = 4
    best_effort_workers: int = 2

    # Batching parameters
    batch_size: int = 50
    batch_timeout_ms: float = 100.0

    @classmethod
    def from_env(cls) -> "PipelineConfig":
        """Load configuration from environment variables."""
        return cls(
            host=os.getenv("PULSEFLOW_HOST", "0.0.0.0"),
            port=int(os.getenv("PULSEFLOW_PORT", "8000")),
            db_path=os.getenv("PULSEFLOW_DB_PATH", "pulseflow.db"),
            queue_backend=os.getenv("PULSEFLOW_QUEUE_BACKEND", "asyncio"),
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"),
            queue_capacity=int(os.getenv("PULSEFLOW_QUEUE_CAPACITY", "1000")),
            critical_workers=int(os.getenv("PULSEFLOW_CRITICAL_WORKERS", "2")),
            normal_workers=int(os.getenv("PULSEFLOW_NORMAL_WORKERS", "4")),
            best_effort_workers=int(os.getenv("PULSEFLOW_BEST_EFFORT_WORKERS", "2")),
            batch_size=int(os.getenv("PULSEFLOW_BATCH_SIZE", "50")),
            batch_timeout_ms=float(os.getenv("PULSEFLOW_BATCH_TIMEOUT_MS", "100.0")),
        )

    @property
    def default_allocation(self) -> Dict[Priority, int]:
        """Default worker allocation mapping per priority lane."""
        return {
            Priority.CRITICAL: self.critical_workers,
            Priority.NORMAL: self.normal_workers,
            Priority.BEST_EFFORT: self.best_effort_workers,
        }

    @property
    def effective_queue_capacity(self) -> Optional[int]:
        """Returns finite queue capacity or None if configured as 0 (unbounded)."""
        return self.queue_capacity if self.queue_capacity > 0 else None


# Shared singleton configuration instance
config = PipelineConfig.from_env()

__all__ = ["PipelineConfig", "config"]

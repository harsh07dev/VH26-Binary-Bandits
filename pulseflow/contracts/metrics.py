"""PulseFlow contracts: Metrics.

Defines the system state snapshot models exposed by the pipeline
for Shrikar's pressure engine/scheduler and Mayur's observability dashboard.
"""

import time
from typing import Optional
from pydantic import BaseModel, Field


class QueueMetrics(BaseModel):
    """Real-time depths and capacities of the priority queues."""
    critical: int = Field(default=0, description="Depth of CRITICAL queue")
    normal: int = Field(default=0, description="Depth of NORMAL queue")
    best_effort: int = Field(default=0, description="Depth of BEST_EFFORT queue")
    total_growth_rate: float = Field(default=0.0, description="Combined rate of change of queue depth (dq/dt)")
    normal_growth_rate: float = Field(default=0.0, description="Rate of change of NORMAL queue depth (dq/dt)")
    best_effort_growth_rate: float = Field(default=0.0, description="Rate of change of BEST_EFFORT queue depth (dq/dt)")

    @property
    def total_depth(self) -> int:
        return self.critical + self.normal + self.best_effort


class WorkerMetrics(BaseModel):
    """Real-time worker allocation and status."""
    critical: int = Field(default=0, description="Workers assigned to CRITICAL")
    normal: int = Field(default=0, description="Workers assigned to NORMAL")
    best_effort: int = Field(default=0, description="Workers assigned to BEST_EFFORT")
    total: int = Field(default=0, description="Total workers in pool")
    active: int = Field(default=0, description="Workers currently processing tasks")
    idle: int = Field(default=0, description="Workers currently idle/waiting")
    utilization: float = Field(default=0.0, description="Worker pool utilization (0.0 to 1.0)")


class BatchingLaneMetrics(BaseModel):
    """Telemetry for a specific adaptive batching lane."""
    current_batch_size: int = Field(default=0)
    previous_batch_size: int = Field(default=0)
    queue_depth: int = Field(default=0)
    growth_rate: float = Field(default=0.0)
    batch_timeout_ms: float = Field(default=0.0)
    increases_count: int = Field(default=0)
    decreases_count: int = Field(default=0)
    last_change_timestamp: float = Field(default=0.0)
    pressure_state: str = Field(default="NORMAL")


class AdaptiveBatchingMetrics(BaseModel):
    """Real-time adaptive batching telemetry per lane."""
    normal: BatchingLaneMetrics = Field(default_factory=BatchingLaneMetrics)
    best_effort: BatchingLaneMetrics = Field(default_factory=BatchingLaneMetrics)


class SystemSnapshot(BaseModel):
    """Complete snapshot of pipeline state exposed via pipeline.get_system_snapshot()."""
    timestamp: float = Field(
        default_factory=time.time,
        description="Snapshot timestamp in epoch seconds",
    )
    # Queue depths (both structured and flattened for easy consumption)
    queues: QueueMetrics = Field(
        default_factory=QueueMetrics,
        description="Detailed queue depths per lane",
    )
    workers: WorkerMetrics = Field(
        default_factory=WorkerMetrics,
        description="Detailed worker allocation per lane",
    )
    batching: Optional[AdaptiveBatchingMetrics] = Field(
        default=None,
        description="Adaptive batching telemetry",
    )

    # Throughput and Latency
    incoming_count: int = Field(default=0, description="Total events ingested since start")
    processed_count: int = Field(default=0, description="Total events successfully processed")
    processing_rate: float = Field(default=0.0, description="Current processing throughput (events/sec)")
    avg_latency_ms: float = Field(default=0.0, description="Average end-to-end processing latency (ms)")
    p95_latency_ms: float = Field(default=0.0, description="95th percentile processing latency (ms)")
    p99_latency_ms: float = Field(default=0.0, description="99th percentile processing latency (ms)")

    # Degradation and Shedding counters
    events_deferred: int = Field(default=0, description="Total events held in deferred status")
    events_sampled: int = Field(default=0, description="Total events processed under sampling")
    events_shed: int = Field(default=0, description="Total best-effort events shed (dropped)")
    critical_events_lost: int = Field(default=0, description="Critical events lost (MUST ALWAYS BE 0)")

    # Shortcut properties for convenient access
    @property
    def critical_queue_depth(self) -> int:
        return self.queues.critical

    @property
    def normal_queue_depth(self) -> int:
        return self.queues.normal

    @property
    def best_queue_depth(self) -> int:
        return self.queues.best_effort

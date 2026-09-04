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

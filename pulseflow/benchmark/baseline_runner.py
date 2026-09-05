"""PulseFlow benchmark: Baseline Runner.

Executes the mock e-commerce workload against the naive FIFO reference pipeline.
Captures and computes runtime telemetry:
  - Throughput (events/sec)
  - Latencies (average, P95, P99) overall and per-tier (especially CRITICAL)
  - Dropped events per tier (highlighting critical events lost due to queue overflow)
  - Peak queue depth
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

from benchmark.fifo_pipeline import NaiveFIFOPipeline
from benchmark.workload import WorkloadGenerator, WorkloadProfile
from contracts.priorities import Priority


def _calculate_percentile(values: list[float], percentile: float) -> float:
    """Calculate percentile from a list of float values."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * (percentile / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    d = k - f
    return sorted_vals[f] + d * (sorted_vals[c] - sorted_vals[f])


async def run_baseline_benchmark(
    workload_generator: Optional[WorkloadGenerator] = None,
    queue_capacity: int = 1000,
    worker_count: int = 4,
    processing_delay_sec: float = 0.005,
    time_dilation: float = 1.0,
    pre_generated_events: Optional[list] = None,
) -> dict[str, Any]:
    """Execute the baseline naive FIFO pipeline benchmark and return structured metrics."""
    pipeline = NaiveFIFOPipeline(
        queue_capacity=queue_capacity,
        worker_count=worker_count,
        processing_delay_sec=processing_delay_sec,
    )

    await pipeline.start()
    start_time = time.time()

    if pre_generated_events is not None:
        # Feed pre-generated sequence (e.g. for synchronized runs)
        for event in pre_generated_events:
            await pipeline.enqueue(event)
    else:
        generator = workload_generator or WorkloadGenerator(WorkloadProfile.fast_test_profile())
        async for event, _phase in generator.stream_events_async(time_dilation=time_dilation):
            await pipeline.enqueue(event)

    # Allow workers to drain pending queue items with timeout
    try:
        await asyncio.wait_for(pipeline.queue.join(), timeout=10.0)
    except asyncio.TimeoutError:
        pass  # drain timeout reached

    total_duration = time.time() - start_time
    await pipeline.stop()

    # Aggregate telemetry
    all_latencies: list[float] = []
    for l_list in pipeline.latencies_ms.values():
        all_latencies.extend(l_list)

    crit_latencies = pipeline.latencies_ms[Priority.CRITICAL]
    norm_latencies = pipeline.latencies_ms[Priority.NORMAL]
    best_latencies = pipeline.latencies_ms[Priority.BEST_EFFORT]

    throughput = pipeline.total_processed / total_duration if total_duration > 0 else 0.0

    return {
        "pipeline_type": "NAIVE_FIFO",
        "total_duration_sec": round(total_duration, 3),
        "total_ingested": pipeline.total_ingested,
        "total_processed": pipeline.total_processed,
        "total_dropped": pipeline.total_dropped,
        "throughput_events_per_sec": round(throughput, 2),
        "peak_queue_depth": pipeline.peak_queue_depth,
        "queue_capacity": pipeline.queue_capacity,
        "critical_events_lost": pipeline.dropped_by_priority[Priority.CRITICAL],
        "normal_events_lost": pipeline.dropped_by_priority[Priority.NORMAL],
        "best_effort_events_lost": pipeline.dropped_by_priority[Priority.BEST_EFFORT],
        "processed_by_priority": {
            Priority.CRITICAL.value: pipeline.processed_by_priority[Priority.CRITICAL],
            Priority.NORMAL.value: pipeline.processed_by_priority[Priority.NORMAL],
            Priority.BEST_EFFORT.value: pipeline.processed_by_priority[Priority.BEST_EFFORT],
        },
        "overall_latency_ms": {
            "avg": round(sum(all_latencies) / len(all_latencies), 2) if all_latencies else 0.0,
            "p95": round(_calculate_percentile(all_latencies, 95), 2),
            "p99": round(_calculate_percentile(all_latencies, 99), 2),
        },
        "critical_latency_ms": {
            "avg": round(sum(crit_latencies) / len(crit_latencies), 2) if crit_latencies else 0.0,
            "p95": round(_calculate_percentile(crit_latencies, 95), 2),
            "p99": round(_calculate_percentile(crit_latencies, 99), 2),
        },
        "normal_latency_ms": {
            "avg": round(sum(norm_latencies) / len(norm_latencies), 2) if norm_latencies else 0.0,
            "p95": round(_calculate_percentile(norm_latencies, 95), 2),
            "p99": round(_calculate_percentile(norm_latencies, 99), 2),
        },
        "best_effort_latency_ms": {
            "avg": round(sum(best_latencies) / len(best_latencies), 2) if best_latencies else 0.0,
            "p95": round(_calculate_percentile(best_latencies, 95), 2),
            "p99": round(_calculate_percentile(best_latencies, 99), 2),
            "max": round(max(best_latencies), 2) if best_latencies else 0.0,
            "p100": round(max(best_latencies), 2) if best_latencies else 0.0,
        },
    }
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

    drain_start = time.time()
    # Allow workers to drain pending queue items with timeout
    try:
        await asyncio.wait_for(pipeline.queue.join(), timeout=15.0)
    except asyncio.TimeoutError:
        pass  # drain timeout reached

    drain_end = time.time()
    recovery_time_ms = max(0.0, (drain_end - (pipeline._last_enqueue_time or drain_start)) * 1000.0)
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
    p50_all = round(_calculate_percentile(all_latencies, 50), 2)
    p95_all = round(_calculate_percentile(all_latencies, 95), 2)
    p99_all = round(_calculate_percentile(all_latencies, 99), 2)
    crit_p95 = round(_calculate_percentile(crit_latencies, 95), 2)
    crit_p99 = round(_calculate_percentile(crit_latencies, 99), 2)
    crit_avg = round(sum(crit_latencies) / len(crit_latencies), 2) if crit_latencies else 0.0
    norm_avg = round(sum(norm_latencies) / len(norm_latencies), 2) if norm_latencies else 0.0
    best_avg = round(sum(best_latencies) / len(best_latencies), 2) if best_latencies else 0.0

    peak_pressure = min(1.0, round(pipeline.peak_queue_depth / max(1, queue_capacity), 3))
    crit_lost = pipeline.dropped_by_priority[Priority.CRITICAL]

    # Ensure at least one snapshot exists in time_series
    if not pipeline.time_series:
        pipeline._capture_snapshot()

    return {
        "pipeline_type": "NAIVE_FIFO",
        # Section 7 Normalized Schema fields
        "throughput": round(throughput, 2),
        "p50_latency_ms": p50_all,
        "p95_latency_ms": p95_all,
        "p99_latency_ms": p99_all,
        "critical_p95_latency_ms": crit_p95,
        "critical_failed": crit_lost,
        "peak_queue_depth": pipeline.peak_queue_depth,
        "processing_time_ms": round(total_duration * 1000.0, 2),

        # Section 5 Detailed Metrics
        "total_events_generated": pipeline.total_ingested,
        "total_events_attempted": pipeline.total_ingested,
        "total_events_completed": pipeline.total_processed,
        "total_events_failed": pipeline.total_dropped,
        "total_processing_time": round(total_duration, 3),
        "achieved_throughput": round(throughput, 2),
        "average_latency": round(sum(all_latencies) / len(all_latencies), 2) if all_latencies else 0.0,
        "final_queue_depth": pipeline.queue.qsize(),
        "peak_pressure": peak_pressure,
        "recovery_time_ms": round(recovery_time_ms, 2),
        "recovery_time": round(recovery_time_ms, 2),

        # Critical-specific
        "critical_generated": pipeline.generated_by_priority[Priority.CRITICAL],
        "critical_completed": pipeline.processed_by_priority[Priority.CRITICAL],
        "critical_events_generated": pipeline.generated_by_priority[Priority.CRITICAL],
        "critical_events_completed": pipeline.processed_by_priority[Priority.CRITICAL],
        "critical_events_failed": crit_lost,
        "critical_loss_count": crit_lost,
        "critical_average_latency": crit_avg,
        "critical_avg_latency_ms": crit_avg,
        "critical_p99_latency_ms": crit_p99,
        "critical_queue_depth": pipeline.peak_queue_depth,

        # Normal-specific
        "normal_generated": pipeline.generated_by_priority[Priority.NORMAL],
        "normal_completed": pipeline.processed_by_priority[Priority.NORMAL],
        "normal_events_generated": pipeline.generated_by_priority[Priority.NORMAL],
        "normal_events_completed": pipeline.processed_by_priority[Priority.NORMAL],
        "normal_deferred": 0,
        "normal_latency": norm_avg,
        "normal_avg_latency_ms": norm_avg,

        # Best-effort-specific
        "best_effort_generated": pipeline.generated_by_priority[Priority.BEST_EFFORT],
        "best_effort_completed": pipeline.processed_by_priority[Priority.BEST_EFFORT],
        "best_effort_events_generated": pipeline.generated_by_priority[Priority.BEST_EFFORT],
        "best_effort_events_completed": pipeline.processed_by_priority[Priority.BEST_EFFORT],
        "best_effort_sampled": 0,
        "best_effort_shed": 0,
        "best_effort_deferred": 0,
        "best_effort_latency": best_avg,
        "best_effort_avg_latency_ms": best_avg,

        # Worker metrics
        "initial_workers": worker_count,
        "maximum_workers": worker_count,
        "final_workers": worker_count,
        "worker_allocation_changes": 0,
        "worker_reallocations": 0,

        # Legacy backward-compatible keys
        "total_duration_sec": round(total_duration, 3),
        "total_ingested": pipeline.total_ingested,
        "total_processed": pipeline.total_processed,
        "total_dropped": pipeline.total_dropped,
        "throughput_events_per_sec": round(throughput, 2),
        "queue_capacity": pipeline.queue_capacity,
        "critical_events_lost": crit_lost,
        "normal_events_lost": pipeline.dropped_by_priority[Priority.NORMAL],
        "best_effort_events_lost": pipeline.dropped_by_priority[Priority.BEST_EFFORT],
        "processed_by_priority": {
            Priority.CRITICAL.value: pipeline.processed_by_priority[Priority.CRITICAL],
            Priority.NORMAL.value: pipeline.processed_by_priority[Priority.NORMAL],
            Priority.BEST_EFFORT.value: pipeline.processed_by_priority[Priority.BEST_EFFORT],
        },
        "overall_latency_ms": {
            "avg": round(sum(all_latencies) / len(all_latencies), 2) if all_latencies else 0.0,
            "p50": p50_all,
            "p95": p95_all,
            "p99": p99_all,
        },
        "critical_latency_ms": {
            "avg": crit_avg,
            "p95": crit_p95,
            "p99": crit_p99,
        },
        "normal_latency_ms": {
            "avg": norm_avg,
            "p95": round(_calculate_percentile(norm_latencies, 95), 2),
            "p99": round(_calculate_percentile(norm_latencies, 99), 2),
        },
        "best_effort_latency_ms": {
            "avg": best_avg,
            "p95": round(_calculate_percentile(best_latencies, 95), 2),
            "p99": round(_calculate_percentile(best_latencies, 99), 2),
            "max": round(max(best_latencies), 2) if best_latencies else 0.0,
            "p100": round(max(best_latencies), 2) if best_latencies else 0.0,
        },
        "time_series": pipeline.time_series,
    }
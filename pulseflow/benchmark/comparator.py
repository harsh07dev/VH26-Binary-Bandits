"""PulseFlow Benchmark: Result Comparator & Advantage Evaluator.

Assembles and normalizes benchmark results into the standardized Section 7 schema,
calculating objective performance deltas and business protection advantages.
"""

from __future__ import annotations

import time
from typing import Any, Dict


def calculate_improvement_percentage(baseline: float, test: float, lower_is_better: bool = True) -> float:
    """Calculate mathematically sound improvement percentage.
    
    If lower_is_better is True (e.g. latency, failures, queue depth):
      improvement = ((baseline - test) / baseline) * 100
    If lower_is_better is False (e.g. throughput):
      improvement = ((test - baseline) / baseline) * 100
    """
    if baseline <= 0.0:
        if test < baseline and lower_is_better:
            return 100.0
        elif test > baseline and not lower_is_better:
            return 100.0
        return 0.0

    if lower_is_better:
        pct = ((baseline - test) / baseline) * 100.0
    else:
        pct = ((test - baseline) / baseline) * 100.0

    return round(pct, 2)


def build_comparison_result(
    benchmark_id: str,
    workload: Dict[str, Any],
    naive_metrics: Dict[str, Any],
    pulseflow_metrics: Dict[str, Any],
    timestamp: float | None = None,
) -> Dict[str, Any]:
    """Construct normalized comparative result object adhering strictly to Section 7 schema."""
    t = timestamp if timestamp is not None else time.time()

    # Latency improvements (lower is better)
    base_crit_p95 = float(naive_metrics.get("critical_p95_latency_ms", 0.0))
    pulse_crit_p95 = float(pulseflow_metrics.get("critical_p95_latency_ms", 0.0))
    crit_p95_gain = calculate_improvement_percentage(base_crit_p95, pulse_crit_p95, lower_is_better=True)

    base_all_p95 = float(naive_metrics.get("p95_latency_ms", 0.0))
    pulse_all_p95 = float(pulseflow_metrics.get("p95_latency_ms", 0.0))
    overall_p95_gain = calculate_improvement_percentage(base_all_p95, pulse_all_p95, lower_is_better=True)

    # Throughput improvement (higher is better)
    base_tp = float(naive_metrics.get("throughput", 0.0))
    pulse_tp = float(pulseflow_metrics.get("throughput", 0.0))
    tp_gain = calculate_improvement_percentage(base_tp, pulse_tp, lower_is_better=False)

    # Backlog & Failure deltas
    base_crit_failed = int(naive_metrics.get("critical_failed", 0))
    pulse_crit_failed = int(pulseflow_metrics.get("critical_failed", 0))
    crit_loss_delta = pulse_crit_failed - base_crit_failed

    base_queue = int(naive_metrics.get("peak_queue_depth", 0))
    pulse_queue = int(pulseflow_metrics.get("peak_queue_depth", 0))
    queue_delta = pulse_queue - base_queue

    base_rec = float(naive_metrics.get("recovery_time_ms", 0.0))
    pulse_rec = float(pulseflow_metrics.get("recovery_time_ms", 0.0))

    pulse_shed = int(pulseflow_metrics.get("best_effort_shed", 0))
    worker_shifts = int(pulseflow_metrics.get("worker_reallocations", 0))

    advantage = {
        "critical_p95_improvement_pct": crit_p95_gain,
        "overall_p95_improvement_pct": overall_p95_gain,
        "throughput_improvement_pct": tp_gain,
        "critical_loss_delta": crit_loss_delta,
        "critical_failures_saved": max(0, base_crit_failed - pulse_crit_failed),
        "peak_queue_reduction": max(0, base_queue - pulse_queue),
        "queue_backlog_delta": queue_delta,
        "recovery_time_delta_ms": round(pulse_rec - base_rec, 2),
        "best_effort_shed_count": pulse_shed,
        "worker_reallocations_count": worker_shifts,
        "best_effort_shed_explanation": (
            "PulseFlow intentionally sacrifices low-priority telemetry (Clicks, Page Views, Logs) "
            "under resource overload in order to protect revenue-critical transactions (Orders, Payments), "
            "guaranteeing zero silent drops and deterministic low latency."
        ),
    }

    return {
        "benchmark_id": benchmark_id,
        "timestamp": round(t, 3),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(t)),
        "workload": workload,
        "naive": naive_metrics,
        "pulseflow": pulseflow_metrics,
        "advantage": advantage,
    }

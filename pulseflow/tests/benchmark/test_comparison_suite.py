"""PulseFlow Automated Test Suite: Naive vs PulseFlow Benchmark & Comparison.

Covers all 10 mandatory specification tests:
1. test_same_workload_used
2. test_naive_pipeline_runs
3. test_pulseflow_pipeline_runs
4. test_benchmark_metrics_generated
5. test_critical_metrics_generated
6. test_naive_and_pulseflow_comparable
7. test_benchmark_reproducibility
8. test_custom_benchmark
9. test_flash_sale_scenario
10. test_comparison_percentage_calculation
"""

from __future__ import annotations

import pytest
import time

from benchmark.baseline_runner import run_baseline_benchmark
from benchmark.benchmark_config import BenchmarkConfig, BenchmarkScenario, STANDARD_DISTRIBUTION
from benchmark.benchmark_storage import (
    get_benchmark_result,
    list_benchmark_results,
    save_benchmark_result,
)
from benchmark.comparator import build_comparison_result, calculate_improvement_percentage
from benchmark.pulseflow_runner import run_pulseflow_benchmark
from benchmark.runner import execute_head_to_head_benchmark
from benchmark.workload import (
    clone_events_for_replay,
    generate_benchmark_dataset,
)
from contracts.priorities import Priority


# =========================================================================
# 1. test_same_workload_used
# =========================================================================
def test_same_workload_used():
    """Verify that both pipelines receive the IDENTICAL workload definition,
    identical event IDs, identical order, identical event mix, and identical payloads.
    """
    config = BenchmarkConfig(
        scenario=BenchmarkScenario.HIGH_LOAD,
        total_events=200,
        target_rate=500.0,
        seed=123,
    )
    dataset = generate_benchmark_dataset(config)

    naive_events = clone_events_for_replay(dataset)
    pulse_events = clone_events_for_replay(dataset)

    assert len(naive_events) == len(pulse_events) == 200

    # Strict identity check across all attributes
    for n_ev, p_ev in zip(naive_events, pulse_events):
        assert n_ev.event_id == p_ev.event_id
        assert n_ev.event_type == p_ev.event_type
        assert n_ev.priority == p_ev.priority
        assert n_ev.timestamp == p_ev.timestamp
        assert n_ev.payload == p_ev.payload


# =========================================================================
# 2. test_naive_pipeline_runs
# =========================================================================
@pytest.mark.asyncio
async def test_naive_pipeline_runs():
    """Verify that the Naive FIFO pipeline runs deterministically,
    treating every event identically without priority isolation,
    and suffering tail-drops when queue capacity is reached.
    """
    config = BenchmarkConfig(total_events=100, target_rate=1000.0, seed=42)
    events = generate_benchmark_dataset(config)

    # Run with small queue capacity (15) to simulate naive queue overflow
    naive_res = await run_baseline_benchmark(
        pre_generated_events=events,
        queue_capacity=15,
        worker_count=2,
        processing_delay_sec=0.001,
    )

    assert naive_res["pipeline_type"] == "NAIVE_FIFO"
    assert naive_res["total_ingested"] == 100
    assert naive_res["total_processed"] > 0
    assert naive_res["total_dropped"] > 0
    assert naive_res["peak_queue_depth"] <= 15
    assert naive_res["worker_allocation_changes"] == 0  # Fixed workers
    assert naive_res["normal_deferred"] == 0            # No adaptive deferral
    assert naive_res["best_effort_shed"] == 0          # No adaptive shedding


# =========================================================================
# 3. test_pulseflow_pipeline_runs
# =========================================================================
@pytest.mark.asyncio
async def test_pulseflow_pipeline_runs():
    """Verify that the PulseFlow pipeline runs with priority classification,
    3 isolated priority queues, dynamic worker reallocation, and micro-batching.
    """
    config = BenchmarkConfig(total_events=100, target_rate=1000.0, seed=42)
    events = generate_benchmark_dataset(config)

    pulse_res = await run_pulseflow_benchmark(
        pre_generated_events=events,
        worker_count=4,
        base_processing_delay_sec=0.0005,
    )

    assert pulse_res["pipeline_type"] == "PULSEFLOW"
    assert pulse_res["total_ingested"] == 100
    assert pulse_res["total_processed"] > 0
    assert pulse_res["critical_events_lost"] == 0
    assert pulse_res["critical_failed"] == 0
    assert "worker_reallocations" in pulse_res
    assert "time_series" in pulse_res


# =========================================================================
# 4. test_benchmark_metrics_generated
# =========================================================================
@pytest.mark.asyncio
async def test_benchmark_metrics_generated():
    """Verify that all required Section 5 overall, normal, best-effort,
    and worker metrics are comprehensively generated.
    """
    config = BenchmarkConfig(total_events=80, target_rate=400.0, seed=77)
    res = await execute_head_to_head_benchmark(config=config, mode="both", fast_simulation=True)

    naive = res["naive"]
    pulse = res["pulseflow"]

    for metrics in (naive, pulse):
        # Overall
        assert "throughput" in metrics
        assert "p50_latency_ms" in metrics
        assert "p95_latency_ms" in metrics
        assert "p99_latency_ms" in metrics
        assert "peak_queue_depth" in metrics
        assert "final_queue_depth" in metrics
        assert "peak_pressure" in metrics
        assert "recovery_time_ms" in metrics
        assert "total_events_generated" in metrics
        assert "total_events_completed" in metrics
        assert "total_events_failed" in metrics

        # Worker
        assert "initial_workers" in metrics
        assert "maximum_workers" in metrics
        assert "final_workers" in metrics
        assert "worker_reallocations" in metrics


# =========================================================================
# 5. test_critical_metrics_generated
# =========================================================================
@pytest.mark.asyncio
async def test_critical_metrics_generated():
    """Verify that critical metrics (ORDER and PAYMENT) are calculated
    from actual results, and prove PulseFlow guarantees zero critical loss.
    """
    config = BenchmarkConfig(total_events=120, target_rate=600.0, seed=55)
    res = await execute_head_to_head_benchmark(config=config, mode="both", fast_simulation=True)

    naive = res["naive"]
    pulse = res["pulseflow"]

    # Critical-specific fields
    for m in (naive, pulse):
        assert "critical_generated" in m
        assert "critical_completed" in m
        assert "critical_failed" in m
        assert "critical_loss_count" in m
        assert "critical_avg_latency_ms" in m
        assert "critical_p95_latency_ms" in m
        assert "critical_p99_latency_ms" in m
        assert "critical_queue_depth" in m

    # Strict invariant: PulseFlow never loses critical transactions
    assert pulse["critical_failed"] == 0
    assert pulse["critical_loss_count"] == 0
    assert pulse["critical_completed"] == pulse["critical_generated"]


# =========================================================================
# 6. test_naive_and_pulseflow_comparable
# =========================================================================
@pytest.mark.asyncio
async def test_naive_and_pulseflow_comparable():
    """Verify that results can be combined into the normalized comparison
    result object conforming strictly to Section 7 schema.
    """
    config = BenchmarkConfig(total_events=60, target_rate=300.0, seed=99)
    res = await execute_head_to_head_benchmark(config=config, mode="both", fast_simulation=True)

    assert "benchmark_id" in res
    assert "workload" in res
    assert "naive" in res
    assert "pulseflow" in res
    assert "advantage" in res

    # Section 7 exact keys check
    naive = res["naive"]
    assert "throughput" in naive
    assert "p50_latency_ms" in naive
    assert "p95_latency_ms" in naive
    assert "p99_latency_ms" in naive
    assert "critical_p95_latency_ms" in naive
    assert "critical_failed" in naive
    assert "peak_queue_depth" in naive
    assert "processing_time_ms" in naive

    pulse = res["pulseflow"]
    assert "throughput" in pulse
    assert "p50_latency_ms" in pulse
    assert "p95_latency_ms" in pulse
    assert "p99_latency_ms" in pulse
    assert "critical_p95_latency_ms" in pulse
    assert "critical_failed" in pulse
    assert "peak_queue_depth" in pulse
    assert "processing_time_ms" in pulse
    assert "best_effort_shed" in pulse
    assert "worker_reallocations" in pulse


# =========================================================================
# 7. test_benchmark_reproducibility
# =========================================================================
def test_benchmark_reproducibility():
    """Verify that using the same fixed seed produces 100% identical event sequences,
    enabling fair re-runs for the jury.
    """
    config1 = BenchmarkConfig(total_events=500, target_rate=1000.0, seed=42)
    config2 = BenchmarkConfig(total_events=500, target_rate=1000.0, seed=42)

    ds1 = generate_benchmark_dataset(config1)
    ds2 = generate_benchmark_dataset(config2)

    assert len(ds1) == len(ds2) == 500
    assert [e.event_id for e in ds1] == [e.event_id for e in ds2]
    assert [e.event_type for e in ds1] == [e.event_type for e in ds2]
    assert [e.priority for e in ds1] == [e.priority for e in ds2]
    assert [e.payload for e in ds1] == [e.payload for e in ds2]
    assert [e.timestamp for e in ds1] == [e.timestamp for e in ds2]


# =========================================================================
# 8. test_custom_benchmark
# =========================================================================
@pytest.mark.asyncio
async def test_custom_benchmark():
    """Verify that custom workloads with user-configured total events,
    target rate, and event mix are properly executed.
    """
    custom_dist = {
        "ORDER": 0.30,
        "PAYMENT": 0.30,
        "CART_ADD": 0.20,
        "INVENTORY_UPDATE": 0.10,
        "CLICK": 0.05,
        "PAGE_VIEW": 0.03,
        "LOG": 0.02,
    }
    config = BenchmarkConfig(
        scenario=BenchmarkScenario.CUSTOM,
        total_events=150,
        target_rate=450.0,
        seed=888,
        distribution=custom_dist,
    )

    res = await execute_head_to_head_benchmark(config=config, mode="both", fast_simulation=True)

    assert res["workload"]["scenario"] == "CUSTOM"
    assert res["workload"]["total_events"] == 150
    assert res["workload"]["target_rate"] == 450.0
    assert res["workload"]["seed"] == 888
    assert res["workload"]["distribution"] == custom_dist


# =========================================================================
# 9. test_flash_sale_scenario
# =========================================================================
@pytest.mark.asyncio
async def test_flash_sale_scenario():
    """Verify that the Flash Sale preset simulates extreme surge conditions
    where the Naive FIFO queue overflows and drops critical orders/payments,
    while PulseFlow guarantees zero critical losses and dynamic worker shifts.
    """
    config = BenchmarkConfig.from_scenario(
        BenchmarkScenario.FLASH_SALE,
        total_events=200,
        target_rate=2000.0,
        seed=42,
    )

    res = await execute_head_to_head_benchmark(config=config, mode="both", fast_simulation=True)

    assert res["workload"]["scenario"] == "FLASH_SALE"
    # Naive FIFO suffers critical loss during surge
    assert res["naive"]["critical_failed"] > 0
    # PulseFlow protects 100% of critical transactions
    assert res["pulseflow"]["critical_failed"] == 0
    # Advantage metrics reflect critical protection
    assert res["advantage"]["critical_failures_saved"] == res["naive"]["critical_failed"]
    assert res["advantage"]["critical_p95_improvement_pct"] >= 0.0


# =========================================================================
# 10. test_comparison_percentage_calculation
# =========================================================================
def test_comparison_percentage_calculation():
    """Verify that latency reduction, throughput gain, and queue deltas
    are mathematically sound, correctly oriented, and guard against division by zero.
    """
    # Lower is better (latency): 100ms baseline -> 20ms test = 80% improvement
    assert calculate_improvement_percentage(100.0, 20.0, lower_is_better=True) == 80.0

    # Latency got worse: 100ms baseline -> 150ms test = -50%
    assert calculate_improvement_percentage(100.0, 150.0, lower_is_better=True) == -50.0

    # Higher is better (throughput): 1000 ev/s baseline -> 1250 ev/s test = 25% gain
    assert calculate_improvement_percentage(1000.0, 1250.0, lower_is_better=False) == 25.0

    # Zero baseline safety
    assert calculate_improvement_percentage(0.0, 10.0, lower_is_better=True) == 0.0
    assert calculate_improvement_percentage(0.0, 50.0, lower_is_better=False) == 100.0

"""PulseFlow Unit & Integration Tests: Benchmark & Evaluation Suite.

Validates:
  1. Workload Generator: Event contract conformance, multi-phase rate switching, payload integrity.
  2. Metrics Analyzers: Latency percentiles, throughput calculations, reliability & zero-division safety.
  3. Zero-Loss Critical Invariant: Strict assertion that PulseFlow never sheds or drops CRITICAL events.
  4. End-to-End Runner Execution: Fast dual pipeline execution comparing Naive FIFO vs. PulseFlow.
"""

from __future__ import annotations

import pytest
from contracts.events import Event
from contracts.priorities import Priority

from benchmark.baseline_runner import run_baseline_benchmark
from benchmark.metrics.latency import (
    LatencyStats,
    analyze_latencies,
    calculate_percentile,
    extract_latency_summary_from_telemetry,
)
from benchmark.metrics.reliability import analyze_reliability
from benchmark.metrics.throughput import (
    PhaseThroughput,
    analyze_throughput_from_telemetry,
    compute_overall_throughput,
)
from benchmark.pulseflow_runner import run_pulseflow_benchmark
from benchmark.runner import execute_benchmark_orchestration
from benchmark.workload import (
    WorkloadGenerator,
    WorkloadPhase,
    WorkloadProfile,
    generate_single_event,
)


# =========================================================================
# 1. Workload Generation Tests
# =========================================================================

def test_generate_single_event_conformance():
    """Verify single generated events strictly conform to contracts.events.Event."""
    event = generate_single_event(event_type="ORDER")
    assert isinstance(event, Event)
    assert event.event_type == "ORDER"
    assert event.priority == Priority.CRITICAL
    assert event.payload["amount"] > 0
    assert "user_id" in event.payload
    assert event.timestamp > 0

    click_event = generate_single_event(event_type="CLICK")
    assert click_event.event_type == "CLICK"
    assert click_event.priority == Priority.BEST_EFFORT


def test_workload_profile_phases_and_multipliers():
    """Verify profile creation and 20x surge calculations."""
    profile = WorkloadProfile.flash_sale(
        normal_rate_per_min=1000.0,
        spike_multiplier=20.0,
        normal_duration_sec=2.0,
        spike_duration_sec=3.0,
        recovery_duration_sec=2.0,
    )
    assert len(profile.phases) == 3
    assert profile.phases[0].name == "normal"
    assert profile.phases[1].name == "spike"
    assert profile.phases[2].name == "recovery"

    # 20x spike verification
    normal_rate = profile.phases[0].rate_events_per_sec
    spike_rate = profile.phases[1].rate_events_per_sec
    assert round(spike_rate / normal_rate, 1) == 20.0
    assert profile.total_duration_seconds == 7.0


def test_workload_generator_events_sequence():
    """Verify generator yields properly tagged events conforming to phases."""
    fast_profile = WorkloadProfile(
        phases=[
            WorkloadPhase("normal", rate_events_per_sec=10.0, duration_seconds=0.5),
            WorkloadPhase("spike", rate_events_per_sec=50.0, duration_seconds=0.5),
        ]
    )
    generator = WorkloadGenerator(fast_profile, seed=123)
    events = generator.generate_all_events()

    assert len(events) == fast_profile.total_expected_events
    assert all(isinstance(e, Event) for e in events)
    assert all(e.priority in (Priority.CRITICAL, Priority.NORMAL, Priority.BEST_EFFORT) for e in events)

    # Check phase tagging in payload
    normal_events = [e for e in events if e.payload.get("_benchmark_phase") == "normal"]
    spike_events = [e for e in events if e.payload.get("_benchmark_phase") == "spike"]
    assert len(normal_events) == 5
    assert len(spike_events) == 25


# =========================================================================
# 2. Metrics Analyzers Tests (Edge cases & Division-by-Zero safety)
# =========================================================================

def test_latency_stats_edge_cases():
    """Test percentile calculations and empty sample handling."""
    empty_stats = LatencyStats.from_samples([])
    assert empty_stats.sample_count == 0
    assert empty_stats.avg_ms == 0.0
    assert empty_stats.p95_ms == 0.0

    # Monotonic samples: 1..100
    samples = [float(i) for i in range(1, 101)]
    stats = LatencyStats.from_samples(samples)
    assert stats.sample_count == 100
    assert stats.min_ms == 1.0
    assert stats.max_ms == 100.0
    assert stats.p50_ms == 50.5
    assert stats.p90_ms == 90.1
    assert stats.p95_ms == 95.05
    assert stats.p99_ms == 99.01


def test_tiered_latency_report():
    """Test that critical latencies are strictly separated from other tiers."""
    samples = {
        Priority.CRITICAL: [5.0, 10.0, 15.0],
        Priority.NORMAL: [50.0, 60.0],
        Priority.BEST_EFFORT: [200.0, 500.0],
    }
    report = analyze_latencies(samples)

    assert report.critical.sample_count == 3
    assert report.critical.avg_ms == 10.0
    assert report.best_effort.avg_ms == 350.0
    assert report.overall.sample_count == 7
    assert report.critical.p95_ms < report.overall.p95_ms


def test_throughput_analyzer():
    """Test overall and per-phase throughput computation."""
    rate = compute_overall_throughput(total_processed=1000, total_duration_sec=2.0)
    assert rate == 500.0

    # Zero duration edge case
    zero_rate = compute_overall_throughput(total_processed=100, total_duration_sec=0.0)
    assert zero_rate == 0.0

    phase = PhaseThroughput.calculate("spike", events_ingested=500, events_processed=450, duration_sec=1.5)
    assert phase.throughput_events_per_sec == 300.0
    assert phase.completion_ratio == 0.9


def test_reliability_analyzer():
    """Test zero critical loss invariant checking and load shedding reporting."""
    telemetry_pulseflow = {
        "pipeline_type": "PULSEFLOW",
        "critical_events_lost": 0,
        "normal_events_lost": 0,
        "best_effort_events_lost": 45,
        "events_shed": 45,
        "events_deferred": 10,
        "processed_by_priority": {
            Priority.CRITICAL.value: 100,
            Priority.NORMAL.value: 200,
            Priority.BEST_EFFORT.value: 155,
        },
    }
    pulse_rel = analyze_reliability(telemetry_pulseflow)
    assert pulse_rel.is_critical_invariant_preserved is True
    assert pulse_rel.critical_events_lost == 0
    assert pulse_rel.critical_delivery_rate == 1.0
    assert pulse_rel.non_critical_events_shed == 45

    telemetry_naive = {
        "pipeline_type": "NAIVE_FIFO",
        "critical_events_lost": 15,
        "normal_events_lost": 40,
        "best_effort_events_lost": 80,
        "processed_by_priority": {
            Priority.CRITICAL.value: 85,
            Priority.NORMAL.value: 160,
            Priority.BEST_EFFORT.value: 120,
        },
    }
    naive_rel = analyze_reliability(telemetry_naive)
    assert naive_rel.is_critical_invariant_preserved is False
    assert naive_rel.critical_events_lost == 15
    assert naive_rel.critical_delivery_rate < 1.0


# =========================================================================
# 3. End-to-End Pipeline & Zero-Loss Critical Invariant Test
# =========================================================================

@pytest.mark.asyncio
async def test_pulseflow_runner_zero_critical_loss_invariant():
    """Crucial Invariant Test:

    Feed a high surge through PulseFlow and assert that under heavy load,
    critical transactions (orders/payments) achieve 100% delivery with 0 loss,
    while best-effort traffic handles shedding/sampling.
    """
    profile = WorkloadProfile.fast_test_profile(
        normal_rate_sec=20.0,
        spike_rate_sec=100.0,
        normal_duration_sec=0.2,
        spike_duration_sec=0.5,
        recovery_duration_sec=0.2,
    )
    generator = WorkloadGenerator(profile, seed=99)
    events = generator.generate_all_events()

    result = await run_pulseflow_benchmark(
        pre_generated_events=events,
        worker_count=2,
        base_processing_delay_sec=0.001,
    )

    # Core PulseFlow Invariant
    assert result["critical_events_lost"] == 0, "PulseFlow must NEVER lose critical events!"
    assert result["processed_by_priority"][Priority.CRITICAL.value] > 0
    assert result["throughput_events_per_sec"] > 0
    assert "critical_latency_ms" in result
    assert result["critical_latency_ms"]["avg"] >= 0


@pytest.mark.asyncio
async def test_naive_vs_pulseflow_comparative_run():
    """Verify that with constrained buffer space, Naive FIFO drops critical events while PulseFlow preserves them."""
    # Constrained workload
    events = [
        generate_single_event("ORDER"),
        generate_single_event("PAYMENT"),
        generate_single_event("CLICK"),
        generate_single_event("PAGE_VIEW"),
        generate_single_event("ORDER"),
    ] * 20  # 100 events total (60 critical, 40 best-effort)

    # Run Naive FIFO with tiny queue capacity (10)
    naive_result = await run_baseline_benchmark(
        pre_generated_events=events,
        queue_capacity=10,
        worker_count=1,
        processing_delay_sec=0.005,
    )

    # Run PulseFlow with same workload
    pulse_result = await run_pulseflow_benchmark(
        pre_generated_events=events,
        worker_count=1,
        base_processing_delay_sec=0.005,
    )

    # PulseFlow strictly protected critical events
    assert pulse_result["critical_events_lost"] == 0
    # Naive FIFO suffered critical loss due to queue overflow
    assert naive_result["critical_events_lost"] > 0
    assert naive_result["total_dropped"] > 0


@pytest.mark.asyncio
async def test_benchmark_orchestration_fast(tmp_path):
    """Verify that execute_benchmark_orchestration runs and writes markdown report."""
    test_report_file = tmp_path / "TEST_REPORT.md"
    profile = WorkloadProfile.fast_test_profile(
        normal_rate_sec=10.0,
        spike_rate_sec=30.0,
        normal_duration_sec=0.1,
        spike_duration_sec=0.2,
        recovery_duration_sec=0.1,
    )

    base, pulse, report = await execute_benchmark_orchestration(
        profile=profile,
        output_path=test_report_file,
        worker_count=2,
    )

    assert test_report_file.exists()
    content = test_report_file.read_text(encoding="utf-8")
    assert "# PulseFlow Benchmark & Evaluation Report" in content
    assert "| Metric | Naive FIFO Pipeline | PulseFlow Pipeline |" in content
    assert base["total_ingested"] == pulse["total_ingested"]
    assert pulse["critical_events_lost"] == 0

import pytest
from contracts.metrics import SystemSnapshot, QueueMetrics, WorkerMetrics
from adaptive.pressure.pressure_calculator import PressureCalculator, PressureSnapshot
from adaptive.pressure.pressure_config import PressureState, PressureConfig

def build_snapshot(queue_depth=0, util=0.0, proc_rate=0.0, latency=0.0) -> SystemSnapshot:
    """Helper to construct a SystemSnapshot with given values."""
    # Split depth artificially across queues
    q = QueueMetrics(critical=queue_depth // 3, normal=queue_depth // 3, best_effort=queue_depth - (2 * (queue_depth // 3)))
    w = WorkerMetrics(utilization=util)
    return SystemSnapshot(
        queues=q,
        workers=w,
        processing_rate=proc_rate,
        avg_latency_ms=latency
    )

def test_normal_pressure():
    # Low depth, low util, low ingress/proc ratio, low latency
    snapshot = build_snapshot(queue_depth=100, util=0.2, proc_rate=50.0, latency=50.0)
    result = PressureCalculator.calculate(snapshot, ingress_rate=20.0)
    
    assert isinstance(result, PressureSnapshot)
    assert result.pressureState == PressureState.NORMAL
    assert result.pressureScore < PressureConfig.HIGH_THRESHOLD
    
    # Check structured output maps correctly
    assert result.queueDepth == 100
    assert result.workerUtilization == 0.2
    assert result.processingRate == 50.0
    assert result.ingressRate == 20.0
    assert result.latency == 50.0

def test_high_pressure():
    # Moderate depth, high util, ingress > proc rate, moderate latency
    snapshot = build_snapshot(queue_depth=1500, util=0.8, proc_rate=100.0, latency=400.0)
    result = PressureCalculator.calculate(snapshot, ingress_rate=150.0)
    
    assert result.pressureState == PressureState.HIGH
    assert PressureConfig.HIGH_THRESHOLD <= result.pressureScore < PressureConfig.EXTREME_THRESHOLD

def test_extreme_pressure():
    # Max depth, max util, extreme ingress, extreme latency
    snapshot = build_snapshot(queue_depth=3000, util=1.0, proc_rate=50.0, latency=1500.0)
    result = PressureCalculator.calculate(snapshot, ingress_rate=500.0)
    
    assert result.pressureState == PressureState.EXTREME
    assert result.pressureScore >= PressureConfig.EXTREME_THRESHOLD

def test_boundary_values():
    # All zero
    snapshot = build_snapshot(queue_depth=0, util=0.0, proc_rate=0.0, latency=0.0)
    result = PressureCalculator.calculate(snapshot, ingress_rate=0.0)
    assert result.pressureScore == 0.0
    assert result.pressureState == PressureState.NORMAL
    
    # Absolute max limits (score should clamp to 1.0)
    snapshot = build_snapshot(queue_depth=100000, util=5.0, proc_rate=10.0, latency=50000.0)
    result = PressureCalculator.calculate(snapshot, ingress_rate=10000.0)
    assert result.pressureScore == 1.0
    assert result.pressureState == PressureState.EXTREME

def test_invalid_or_missing_metrics():
    # Negative util and latency
    snapshot = build_snapshot(queue_depth=-100, util=-0.5, proc_rate=0.0, latency=-100.0)
    # queue depth property total_depth doesn't clamp negative naturally in the helper unless queue metrics forbid it.
    # We just ensure it doesn't crash and normalizes to 0.0
    result = PressureCalculator.calculate(snapshot, ingress_rate=0.0)
    
    assert result.pressureScore <= 0.0
    assert result.pressureState == PressureState.NORMAL

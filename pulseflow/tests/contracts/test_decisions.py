"""Unit tests for PulseFlow contracts: Actions, Decisions, and Metrics."""

import pytest
from pydantic import ValidationError
from contracts.priorities import Priority
from contracts.actions import Action
from contracts.decisions import (
    ProcessingDecision,
    SystemDecision,
    InvalidDecisionError,
    validate_decision_for_event,
)
from contracts.metrics import QueueMetrics, WorkerMetrics, SystemSnapshot


def test_action_enum_and_parsing():
    assert Action.STREAM.value == "STREAM"
    assert Action.BATCH.value == "BATCH"
    assert Action.DEFER.value == "DEFER"
    assert Action.SAMPLE.value == "SAMPLE"
    assert Action.SHED.value == "SHED"

    assert Action.from_str("stream") == Action.STREAM
    assert Action.from_str("BATCH") == Action.BATCH
    assert Action.from_str("defer") == Action.DEFER


def test_valid_processing_decisions():
    # Critical streaming
    d1 = ProcessingDecision(priority=Priority.CRITICAL, action=Action.STREAM, target_workers=4)
    assert d1.priority == Priority.CRITICAL
    assert d1.action == Action.STREAM

    # Normal micro-batching
    d2 = ProcessingDecision(priority=Priority.NORMAL, action=Action.BATCH, batch_size=50, batch_timeout_ms=100.0)
    assert d2.batch_size == 50
    assert d2.batch_timeout_ms == 100.0

    # Best-effort sampling
    d3 = ProcessingDecision(priority=Priority.BEST_EFFORT, action=Action.SAMPLE, sample_rate=0.20)
    assert d3.sample_rate == 0.20

    # Best-effort shedding
    d4 = ProcessingDecision(priority=Priority.BEST_EFFORT, action=Action.SHED)
    assert d4.action == Action.SHED


def test_critical_shed_protection():
    """CRITICAL events must never be shed or sampled below 100%."""
    # Instantiation validation
    with pytest.raises(ValidationError):
        ProcessingDecision(priority=Priority.CRITICAL, action=Action.SHED)

    with pytest.raises(ValidationError):
        ProcessingDecision(priority=Priority.CRITICAL, action=Action.SAMPLE, sample_rate=0.5)

    # Runtime guard validation
    illegal_shed = ProcessingDecision(priority=Priority.BEST_EFFORT, action=Action.SHED)
    with pytest.raises(InvalidDecisionError):
        validate_decision_for_event(Priority.CRITICAL, illegal_shed)


def test_system_decision():
    sys_dec = SystemDecision(
        pressure=0.85,
        lane_decisions={
            Priority.CRITICAL: ProcessingDecision(priority=Priority.CRITICAL, action=Action.STREAM, target_workers=4),
            Priority.NORMAL: ProcessingDecision(priority=Priority.NORMAL, action=Action.BATCH, batch_size=50),
            Priority.BEST_EFFORT: ProcessingDecision(priority=Priority.BEST_EFFORT, action=Action.SHED, target_workers=0),
        },
        worker_allocation={
            Priority.CRITICAL: 4,
            Priority.NORMAL: 4,
            Priority.BEST_EFFORT: 0,
        },
    )
    assert sys_dec.pressure == 0.85
    assert sys_dec.get_workers_for_lane(Priority.CRITICAL) == 4
    assert sys_dec.get_lane_decision(Priority.BEST_EFFORT).action == Action.SHED


def test_metrics_models():
    queues = QueueMetrics(critical=10, normal=400, best_effort=3200)
    assert queues.total_depth == 3610

    workers = WorkerMetrics(critical=3, normal=4, best_effort=1, total=8, active=7, idle=1, utilization=0.875)
    snapshot = SystemSnapshot(
        queues=queues,
        workers=workers,
        incoming_count=10000,
        processed_count=9500,
        processing_rate=1700.0,
        avg_latency_ms=12.4,
        critical_events_lost=0,
    )

    assert snapshot.critical_queue_depth == 10
    assert snapshot.normal_queue_depth == 400
    assert snapshot.best_queue_depth == 3200
    assert snapshot.critical_events_lost == 0

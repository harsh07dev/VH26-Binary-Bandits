import pytest
import asyncio
from contracts.events import Event
from contracts.priorities import Priority
from contracts.actions import Action
from contracts.metrics import SystemSnapshot, QueueMetrics, WorkerMetrics
from adaptive.pressure.pressure_config import PressureState

from adaptive.scheduler.decision_engine import DecisionEngine, AdaptiveDecision
from adaptive.queues.adaptive_queue import AdaptiveQueueRouter
from pipeline.workers.worker_pool import worker_pool


@pytest.fixture(autouse=True)
async def cleanup():
    AdaptiveQueueRouter.clear_all()
    if worker_pool.is_running:
        await worker_pool.stop()
    yield
    AdaptiveQueueRouter.clear_all()
    if worker_pool.is_running:
        await worker_pool.stop()


def build_snapshot(queue_depth, util, latency) -> SystemSnapshot:
    return SystemSnapshot(
        queues=QueueMetrics(critical=queue_depth // 3, normal=queue_depth // 3, best_effort=queue_depth // 3),
        workers=WorkerMetrics(utilization=util),
        avg_latency_ms=latency,
        processing_rate=50.0
    )


@pytest.mark.asyncio
async def test_normal_traffic():
    # Low pressure snapshot
    snapshot = build_snapshot(queue_depth=10, util=0.2, latency=50.0)
    event = Event(event_type="CART_ADD") # NORMAL
    
    decision = await DecisionEngine.process_event(event, snapshot, ingress_rate=10.0)
    
    assert isinstance(decision, AdaptiveDecision)
    assert decision.pressure_state == PressureState.NORMAL
    assert decision.priority == Priority.NORMAL
    assert decision.strategy == Action.STREAM
    
    # Event should be enqueued
    metrics = AdaptiveQueueRouter.get_metrics()
    assert metrics["normalQueueDepth"] == 1


@pytest.mark.asyncio
async def test_high_pressure():
    # High pressure snapshot
    snapshot = build_snapshot(queue_depth=1500, util=0.8, latency=400.0)
    event = Event(event_type="CART_ADD") # NORMAL
    
    decision = await DecisionEngine.process_event(event, snapshot, ingress_rate=200.0)
    
    assert decision.pressure_state == PressureState.HIGH
    assert decision.priority == Priority.NORMAL
    assert decision.strategy == Action.BATCH # Normal degrades to batch


@pytest.mark.asyncio
async def test_extreme_pressure_critical_event():
    # Extreme pressure
    snapshot = build_snapshot(queue_depth=3000, util=1.0, latency=1500.0)
    event = Event(event_type="ORDER") # CRITICAL
    
    decision = await DecisionEngine.process_event(event, snapshot, ingress_rate=500.0)
    
    assert decision.pressure_state == PressureState.EXTREME
    assert decision.priority == Priority.CRITICAL
    assert decision.strategy == Action.STREAM # Protected lane
    
    # Critical event must always be enqueued
    metrics = AdaptiveQueueRouter.get_metrics()
    assert metrics["criticalQueueDepth"] == 1


@pytest.mark.asyncio
async def test_extreme_pressure_best_effort_event():
    # Extreme pressure
    snapshot = build_snapshot(queue_depth=3000, util=1.0, latency=1500.0)
    event = Event(event_type="CLICK") # BEST_EFFORT
    
    decision = await DecisionEngine.process_event(event, snapshot, ingress_rate=500.0)
    
    assert decision.pressure_state == PressureState.EXTREME
    assert decision.priority == Priority.BEST_EFFORT
    assert decision.strategy == Action.SHED # Should be shed
    
    # Best effort event should NOT be enqueued because it was shed
    metrics = AdaptiveQueueRouter.get_metrics()
    assert metrics["bestEffortQueueDepth"] == 0


@pytest.mark.asyncio
async def test_worker_reallocation():
    # Test that the decision engine actually instructs the worker pool
    snapshot = build_snapshot(queue_depth=3000, util=1.0, latency=1500.0)
    event = Event(event_type="ORDER")
    
    # Start the pool with NORMAL allocation so it is running
    await worker_pool.start()
    
    # Process event under EXTREME pressure
    decision = await DecisionEngine.process_event(event, snapshot, ingress_rate=500.0)
    
    assert decision.pressure_state == PressureState.EXTREME
    
    # Verify the pool was reallocated dynamically
    actual_allocation = worker_pool.get_allocation()
    assert actual_allocation[Priority.CRITICAL] == 4
    assert actual_allocation[Priority.NORMAL] == 4
    assert actual_allocation[Priority.BEST_EFFORT] == 0


@pytest.mark.asyncio
async def test_high_pressure_best_effort_sample_dropped():
    from adaptive.sampling.sampler import ProbabilisticSampler
    # High pressure snapshot
    snapshot = build_snapshot(queue_depth=1500, util=0.8, latency=400.0)
    event = Event(event_type="CLICK")  # BEST_EFFORT

    # Sampler configured to drop all events (rate = 0.0)
    dropping_sampler = ProbabilisticSampler(sample_rate=0.0)
    decision = await DecisionEngine.process_event(
        event, snapshot, ingress_rate=200.0, sampler=dropping_sampler
    )

    assert decision.pressure_state == PressureState.HIGH
    assert decision.priority == Priority.BEST_EFFORT
    assert decision.strategy == Action.SAMPLE
    assert decision.kept is False

    # Event must NOT enter the best effort queue
    metrics = AdaptiveQueueRouter.get_metrics()
    assert metrics["bestEffortQueueDepth"] == 0


@pytest.mark.asyncio
async def test_high_pressure_best_effort_sample_kept():
    from adaptive.sampling.sampler import ProbabilisticSampler
    # High pressure snapshot
    snapshot = build_snapshot(queue_depth=1500, util=0.8, latency=400.0)
    event = Event(event_type="CLICK")  # BEST_EFFORT

    # Sampler configured to keep all events (rate = 1.0)
    keeping_sampler = ProbabilisticSampler(sample_rate=1.0)
    decision = await DecisionEngine.process_event(
        event, snapshot, ingress_rate=200.0, sampler=keeping_sampler
    )

    assert decision.pressure_state == PressureState.HIGH
    assert decision.priority == Priority.BEST_EFFORT
    assert decision.strategy == Action.SAMPLE
    assert decision.kept is True

    # Kept event MUST enter the best effort queue
    metrics = AdaptiveQueueRouter.get_metrics()
    assert metrics["bestEffortQueueDepth"] == 1


@pytest.mark.asyncio
async def test_high_pressure_critical_unaffected_by_sampler():
    from adaptive.sampling.sampler import ProbabilisticSampler
    # High pressure snapshot
    snapshot = build_snapshot(queue_depth=1500, util=0.8, latency=400.0)
    event = Event(event_type="ORDER")  # CRITICAL

    # Even with a 0.0 sample rate, CRITICAL events are never sampled or dropped
    dropping_sampler = ProbabilisticSampler(sample_rate=0.0)
    decision = await DecisionEngine.process_event(
        event, snapshot, ingress_rate=200.0, sampler=dropping_sampler
    )

    assert decision.pressure_state == PressureState.HIGH
    assert decision.priority == Priority.CRITICAL
    assert decision.strategy == Action.STREAM
    assert decision.kept is True

    # Critical event must enter the critical queue
    metrics = AdaptiveQueueRouter.get_metrics()
    assert metrics["criticalQueueDepth"] == 1


def test_metrics_tracker_sample_stats():
    from adaptive.scheduler.metrics_tracker import adaptive_metrics
    adaptive_metrics.reset()

    # Create dummy decisions
    kept_decision = AdaptiveDecision(
        event_id="evt-1",
        priority=Priority.BEST_EFFORT,
        pressure_state=PressureState.HIGH,
        pressure_score=0.6,
        strategy=Action.SAMPLE,
        queue_depth=50,
        worker_allocation={Priority.CRITICAL: 3, Priority.NORMAL: 4, Priority.BEST_EFFORT: 1},
        decision_reason="Sampling under high pressure",
        kept=True
    )
    dropped_decision = AdaptiveDecision(
        event_id="evt-2",
        priority=Priority.BEST_EFFORT,
        pressure_state=PressureState.HIGH,
        pressure_score=0.6,
        strategy=Action.SAMPLE,
        queue_depth=50,
        worker_allocation={Priority.CRITICAL: 3, Priority.NORMAL: 4, Priority.BEST_EFFORT: 1},
        decision_reason="Sampling under high pressure",
        kept=False
    )

    adaptive_metrics.record_decision(kept_decision)
    assert adaptive_metrics.shed_stats["sampled"] == 1
    assert adaptive_metrics.shed_stats["sampled_kept"] == 1
    assert adaptive_metrics.shed_stats["sampled_dropped"] == 0

    adaptive_metrics.record_decision(dropped_decision)
    assert adaptive_metrics.shed_stats["sampled"] == 2
    assert adaptive_metrics.shed_stats["sampled_kept"] == 1
    assert adaptive_metrics.shed_stats["sampled_dropped"] == 1


@pytest.mark.asyncio
async def test_decision_engine_adaptive_batching_integration():
    from adaptive.allocation.batch_sizer import batch_sizer
    
    # Temporarily bypass hysteresis for easy testing
    original_consecutive = batch_sizer.config.consecutive_samples_required
    batch_sizer.config.consecutive_samples_required = 1
    
    # 1. Stable queue -> batch remains stable
    # Force cooldown to expire
    batch_sizer._last_adjustment_time = 0.0
    
    # Setup worker pool with NORMAL workers
    await worker_pool.start(initial_allocation={Priority.NORMAL: 2})
    
    snapshot_stable = build_snapshot(queue_depth=50, util=0.5, latency=100.0)
    # inject growth rate
    snapshot_stable.queues.normal_growth_rate = 1.0 # Stable (between -2 and 5)
    
    # Process event
    event = Event(event_type="CART_ADD")
    await DecisionEngine.process_event(event, snapshot_stable)
    
    workers = worker_pool.get_workers(Priority.NORMAL)
    initial_batch_size = workers[0].batch_size
    assert initial_batch_size == 50 # Default min batch size
    
    # 2. Queue Growth -> batch increases
    batch_sizer._last_adjustment_time = 0.0
    snapshot_grow = build_snapshot(queue_depth=100, util=0.8, latency=200.0)
    snapshot_grow.queues.normal_growth_rate = 10.0 # Growing > 5.0
    
    await DecisionEngine.process_event(event, snapshot_grow)
    
    workers = worker_pool.get_workers(Priority.NORMAL)
    increased_batch_size = workers[0].batch_size
    assert increased_batch_size > initial_batch_size
    assert increased_batch_size == 75 # Next step up from 50
    
    # 3. Queue Drain -> batch decreases
    batch_sizer._last_adjustment_time = 0.0
    snapshot_drain = build_snapshot(queue_depth=80, util=0.6, latency=150.0)
    snapshot_drain.queues.normal_growth_rate = -5.0 # Draining < -2.0
    
    await DecisionEngine.process_event(event, snapshot_drain)
    
    workers = worker_pool.get_workers(Priority.NORMAL)
    decreased_batch_size = workers[0].batch_size
    assert decreased_batch_size < increased_batch_size
    assert decreased_batch_size == 50 # Stepped down back to 50
    
    # Restore config
    batch_sizer.config.consecutive_samples_required = original_consecutive


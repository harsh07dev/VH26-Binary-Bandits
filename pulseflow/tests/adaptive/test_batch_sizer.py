import time
import pytest
from pydantic import BaseModel

from contracts.priorities import Priority
from adaptive.allocation.batch_sizer import AdaptiveBatchSizer, BatchSizingConfig


class MockQueues:
    def __init__(self, normal_growth_rate: float, best_effort_growth_rate: float, normal_depth: int, best_effort_depth: int):
        self.normal_growth_rate = normal_growth_rate
        self.best_effort_growth_rate = best_effort_growth_rate
        self.normal = normal_depth
        self.best_effort = best_effort_depth
        self.total_depth = normal_depth + best_effort_depth


class MockSnapshot:
    def __init__(self, normal_growth: float = 0.0, best_effort_growth: float = 0.0, normal_depth: int = 50, best_effort_depth: int = 50):
        self.queues = MockQueues(normal_growth, best_effort_growth, normal_depth, best_effort_depth)


def test_batch_sizer_initialization():
    sizer = AdaptiveBatchSizer()
    assert sizer._current_sizes[Priority.NORMAL] == 50
    assert sizer._current_sizes[Priority.BEST_EFFORT] == 100


def test_batch_sizer_growth_requires_consecutive_samples():
    config = BatchSizingConfig(adjustment_cooldown_sec=0.0, consecutive_samples_required=2)
    sizer = AdaptiveBatchSizer(config)
    
    # NORMAL is growing, BEST_EFFORT is stable
    snapshot = MockSnapshot(normal_growth=10.0, best_effort_growth=1.0)
    
    # First sample: no change yet
    sizes1 = sizer.calculate(snapshot)
    assert sizes1[Priority.NORMAL] == 50
    assert sizes1[Priority.BEST_EFFORT] == 100
    
    # Second sample: triggers growth to next step (75) only for NORMAL
    sizes2 = sizer.calculate(snapshot)
    assert sizes2[Priority.NORMAL] == 75
    assert sizes2[Priority.BEST_EFFORT] == 100 # Should not grow


def test_batch_sizer_shrink_requires_consecutive_samples():
    config = BatchSizingConfig(adjustment_cooldown_sec=0.0, consecutive_samples_required=2)
    sizer = AdaptiveBatchSizer(config)
    
    # Initialize higher
    sizer._current_sizes[Priority.NORMAL] = 200
    sizer._current_sizes[Priority.BEST_EFFORT] = 400
    
    # BEST_EFFORT is shrinking, NORMAL is stable
    snapshot = MockSnapshot(normal_growth=1.0, best_effort_growth=-5.0)
    
    # First sample: no change yet
    sizes1 = sizer.calculate(snapshot)
    assert sizes1[Priority.BEST_EFFORT] == 400
    
    # Second sample: triggers shrink to previous step only for BEST_EFFORT
    sizes2 = sizer.calculate(snapshot)
    assert sizes2[Priority.NORMAL] == 200 # Should not shrink
    assert sizes2[Priority.BEST_EFFORT] == 300


def test_batch_sizer_cooldown():
    config = BatchSizingConfig(adjustment_cooldown_sec=1.0, consecutive_samples_required=1)
    sizer = AdaptiveBatchSizer(config)
    
    snapshot = MockSnapshot(normal_growth=10.0)
    now = time.time()
    
    # First adjustment should work (50 -> 75)
    sizes1 = sizer.calculate(snapshot, now=now)
    assert sizes1[Priority.NORMAL] == 75
    
    # Immediate second adjustment should be ignored due to cooldown
    sizes2 = sizer.calculate(snapshot, now=now + 0.1)
    assert sizes2[Priority.NORMAL] == 75
    
    # Adjustment after cooldown should work (75 -> 100)
    sizes3 = sizer.calculate(snapshot, now=now + 1.1)
    assert sizes3[Priority.NORMAL] == 100


def test_batch_sizer_bounds():
    config = BatchSizingConfig(min_batch_size=50, max_batch_size=200, adjustment_cooldown_sec=0.0, consecutive_samples_required=1)
    sizer = AdaptiveBatchSizer(config)
    
    # Max out
    sizer._current_sizes[Priority.NORMAL] = 200
    snapshot_grow = MockSnapshot(normal_growth=10.0, normal_depth=500)
    sizes = sizer.calculate(snapshot_grow)
    assert sizes[Priority.NORMAL] == 200  # Should not exceed max
    
    # Min out
    sizer._current_sizes[Priority.NORMAL] = 50
    snapshot_shrink = MockSnapshot(normal_growth=-5.0, normal_depth=50)
    sizes = sizer.calculate(snapshot_shrink)
    assert sizes[Priority.NORMAL] == 50  # Should not drop below min


def test_batch_sizer_latency_protection_low_queue():
    config = BatchSizingConfig(min_batch_size=50, low_queue_threshold=10, adjustment_cooldown_sec=0.0)
    sizer = AdaptiveBatchSizer(config)
    
    # Simulate a spike that increased batch size to 200
    sizer._current_sizes[Priority.NORMAL] = 200
    sizer._current_sizes[Priority.BEST_EFFORT] = 400
    
    # Suddenly traffic falls, depth drops below threshold for both queues
    snapshot_low = MockSnapshot(normal_growth=0.0, best_effort_growth=0.0, normal_depth=5, best_effort_depth=5)
    sizes = sizer.calculate(snapshot_low)
    
    # Should aggressively shrink to min limits ignoring consecutive samples
    assert sizes[Priority.NORMAL] == 50
    assert sizes[Priority.BEST_EFFORT] == 100

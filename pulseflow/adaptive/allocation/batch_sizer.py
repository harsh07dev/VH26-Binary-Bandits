"""PulseFlow adaptive: Stateful Batch Sizer.

Maintains the state of dynamically scaling batch sizes to prevent thrashing
and excessive updates. Evaluates queue growth rates (dq/dt) to incrementally
adjust batch sizes up or down.
"""

import time
from typing import Dict, Optional
from pydantic import BaseModel, Field

from contracts.priorities import Priority
from contracts.metrics import SystemSnapshot


class BatchSizingConfig(BaseModel):
    """Configuration constraints for dynamic batch sizing."""
    min_batch_size: int = Field(default=50, ge=1)
    max_batch_size: int = Field(default=400, ge=1)
    growth_threshold_dqdt: float = Field(default=5.0, description="dq/dt above this triggers growth")
    drain_threshold_dqdt: float = Field(default=-2.0, description="dq/dt below this triggers shrink")
    low_queue_threshold: int = Field(default=10, description="If total depth < this, trigger fast flush")
    adjustment_cooldown_sec: float = Field(default=1.0, description="Minimum time between adjustments")
    consecutive_samples_required: int = Field(default=2, description="Consecutive signals required to adjust")


class AdaptiveBatchSizer:
    """Stateful batch size controller using dq/dt telemetry."""

    # Bounded stepwise growth stages
    STEPS = [25, 50, 75, 100, 150, 200, 300, 400, 600, 800, 1000]

    def __init__(self, config: Optional[BatchSizingConfig] = None) -> None:
        self.config = config or BatchSizingConfig()
        
        # Initialize with baseline batch sizes
        self._current_sizes: Dict[Priority, int] = {
            Priority.CRITICAL: 1,  # Critical does not batch, but keep state for consistency
            Priority.NORMAL: self.config.min_batch_size,
            Priority.BEST_EFFORT: min(self.config.max_batch_size, self.config.min_batch_size * 2),
        }
        
        self._last_adjustment_time: float = 0.0
        
        # Independent consecutive counters
        self._consecutive_grow: Dict[Priority, int] = {Priority.NORMAL: 0, Priority.BEST_EFFORT: 0}
        self._consecutive_shrink: Dict[Priority, int] = {Priority.NORMAL: 0, Priority.BEST_EFFORT: 0}
        
        # Metrics Tracking
        self._previous_sizes: Dict[Priority, int] = dict(self._current_sizes)
        self._increases_count: Dict[Priority, int] = {Priority.NORMAL: 0, Priority.BEST_EFFORT: 0}
        self._decreases_count: Dict[Priority, int] = {Priority.NORMAL: 0, Priority.BEST_EFFORT: 0}
        self._last_change_timestamp: Dict[Priority, float] = {Priority.NORMAL: 0.0, Priority.BEST_EFFORT: 0.0}

    def _get_next_step(self, current: int, up: bool) -> int:
        """Find the next bounded step size."""
        if up:
            for step in self.STEPS:
                if step > current:
                    return min(step, self.config.max_batch_size)
            return self.config.max_batch_size
        else:
            for step in reversed(self.STEPS):
                if step < current:
                    return max(step, self.config.min_batch_size)
            return self.config.min_batch_size

    def _evaluate_lane(self, priority: Priority, growth_rate: float, depth: int) -> bool:
        """Evaluate and update a single priority lane independently."""
        needs_update = False
        
        if depth <= self.config.low_queue_threshold:
            # Latency Protection: queue is virtually empty. Shrink aggressively.
            new_size = self.config.min_batch_size
            if priority == Priority.BEST_EFFORT:
                new_size = min(self.config.max_batch_size, self.config.min_batch_size * 2)
                
            if new_size != self._current_sizes[priority]:
                self._previous_sizes[priority] = self._current_sizes[priority]
                self._current_sizes[priority] = new_size
                self._decreases_count[priority] += 1
                self._last_change_timestamp[priority] = time.time()
                needs_update = True
                
            self._consecutive_grow[priority] = 0
            self._consecutive_shrink[priority] = 0
            
        elif growth_rate > self.config.growth_threshold_dqdt:
            self._consecutive_grow[priority] += 1
            self._consecutive_shrink[priority] = 0
            if self._consecutive_grow[priority] >= self.config.consecutive_samples_required:
                new_size = self._get_next_step(self._current_sizes[priority], up=True)
                if new_size != self._current_sizes[priority]:
                    self._previous_sizes[priority] = self._current_sizes[priority]
                    self._current_sizes[priority] = new_size
                    self._increases_count[priority] += 1
                    self._last_change_timestamp[priority] = time.time()
                    needs_update = True
                self._consecutive_grow[priority] = 0

        elif growth_rate < self.config.drain_threshold_dqdt:
            self._consecutive_shrink[priority] += 1
            self._consecutive_grow[priority] = 0
            if self._consecutive_shrink[priority] >= self.config.consecutive_samples_required:
                new_size = self._get_next_step(self._current_sizes[priority], up=False)
                if new_size != self._current_sizes[priority]:
                    self._previous_sizes[priority] = self._current_sizes[priority]
                    self._current_sizes[priority] = new_size
                    self._decreases_count[priority] += 1
                    self._last_change_timestamp[priority] = time.time()
                    needs_update = True
                self._consecutive_shrink[priority] = 0
        else:
            # Stable queue -> reset counters (hysteresis)
            self._consecutive_grow[priority] = 0
            self._consecutive_shrink[priority] = 0
            
        return needs_update

    def calculate(
        self,
        snapshot: SystemSnapshot,
        now: Optional[float] = None
    ) -> Dict[Priority, int]:
        """Evaluate telemetry and return the optimal batch sizes per lane."""
        now = now if now is not None else time.time()
        
        # Enforce cooldown to prevent rapid oscillation/thrashing
        if now - self._last_adjustment_time < self.config.adjustment_cooldown_sec:
            return dict(self._current_sizes)

        # Retrieve independent growth rates and depths
        normal_dq_dt = getattr(snapshot.queues, 'normal_growth_rate', 0.0)
        best_dq_dt = getattr(snapshot.queues, 'best_effort_growth_rate', 0.0)
        
        normal_depth = snapshot.queues.normal
        best_depth = snapshot.queues.best_effort
        
        update_normal = self._evaluate_lane(Priority.NORMAL, normal_dq_dt, normal_depth)
        update_best = self._evaluate_lane(Priority.BEST_EFFORT, best_dq_dt, best_depth)
        
        if update_normal or update_best:
            self._last_adjustment_time = now

        return dict(self._current_sizes)

    def get_metrics(
        self, snapshot: SystemSnapshot, pressure_state: str, batch_timeout_ms: float
    ):
        from contracts.metrics import AdaptiveBatchingMetrics, BatchingLaneMetrics
        
        normal_metrics = BatchingLaneMetrics(
            current_batch_size=self._current_sizes[Priority.NORMAL],
            previous_batch_size=self._previous_sizes[Priority.NORMAL],
            queue_depth=snapshot.queues.normal,
            growth_rate=getattr(snapshot.queues, "normal_growth_rate", 0.0),
            batch_timeout_ms=batch_timeout_ms,
            increases_count=self._increases_count[Priority.NORMAL],
            decreases_count=self._decreases_count[Priority.NORMAL],
            last_change_timestamp=self._last_change_timestamp[Priority.NORMAL],
            pressure_state=pressure_state
        )
        
        best_metrics = BatchingLaneMetrics(
            current_batch_size=self._current_sizes[Priority.BEST_EFFORT],
            previous_batch_size=self._previous_sizes[Priority.BEST_EFFORT],
            queue_depth=snapshot.queues.best_effort,
            growth_rate=getattr(snapshot.queues, "best_effort_growth_rate", 0.0),
            batch_timeout_ms=batch_timeout_ms,
            increases_count=self._increases_count[Priority.BEST_EFFORT],
            decreases_count=self._decreases_count[Priority.BEST_EFFORT],
            last_change_timestamp=self._last_change_timestamp[Priority.BEST_EFFORT],
            pressure_state=pressure_state
        )
        
        return AdaptiveBatchingMetrics(
            normal=normal_metrics,
            best_effort=best_metrics
        )


# Singleton instance
batch_sizer = AdaptiveBatchSizer()

__all__ = ["BatchSizingConfig", "AdaptiveBatchSizer", "batch_sizer"]

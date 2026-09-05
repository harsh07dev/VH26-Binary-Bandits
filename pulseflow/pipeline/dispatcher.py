"""PulseFlow pipeline: Dispatcher.

Coordinates task pulling across priority queues with Lazy Priority Aging (Anti-Starvation).

Key Mechanics:
- When pulling tasks from NORMAL, inspect the head timestamp of BEST_EFFORT.
- If (current_time - head.timestamp) > threshold (default 5.0s), promote and process that BEST_EFFORT item first.
- Safety Rule: Restrict priority aging strictly to stateless event types (CLICK, PAGE_VIEW, LOG).
  Exclude stateful types (CART_ADD, INVENTORY_UPDATE, ORDER, PAYMENT) to prevent causal inversion
  and out-of-order execution bugs.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Set, Union

from contracts.events import Event
from contracts.priorities import Priority
from pipeline.queues.abstract_queue import QueueEmpty
from pipeline.queues.queue_manager import QueueManager, queue_manager

# Strictly stateless event types eligible for priority aging
STATELESS_EVENT_TYPES: frozenset[str] = frozenset({"CLICK", "PAGE_VIEW", "LOG"})

# Stateful event types strictly prohibited from priority aging to preserve causal consistency
STATEFUL_EVENT_TYPES: frozenset[str] = frozenset({
    "CART_ADD",
    "INVENTORY_UPDATE",
    "ORDER",
    "PAYMENT",
})

DEFAULT_AGING_THRESHOLD_SEC: float = 5.0


@dataclass
class AgingStats:
    """Metrics tracking Lazy Priority Aging operations."""
    evaluated_count: int = 0
    promoted_count: int = 0
    skipped_stateful_count: int = 0
    skipped_not_expired_count: int = 0
    last_promoted_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evaluated_count": self.evaluated_count,
            "promoted_count": self.promoted_count,
            "skipped_stateful_count": self.skipped_stateful_count,
            "skipped_not_expired_count": self.skipped_not_expired_count,
            "last_promoted_at": self.last_promoted_at,
        }


def is_stateless_event(event_or_type: Union[Event, str]) -> bool:
    """Check if an event or event type string is strictly stateless."""
    event_type = event_or_type.event_type if isinstance(event_or_type, Event) else event_or_type
    return event_type.strip().upper() in STATELESS_EVENT_TYPES


def is_stateful_event(event_or_type: Union[Event, str]) -> bool:
    """Check if an event or event type string is stateful."""
    event_type = event_or_type.event_type if isinstance(event_or_type, Event) else event_or_type
    return event_type.strip().upper() in STATEFUL_EVENT_TYPES


class Dispatcher:
    """Task dispatcher implementing Lazy Priority Aging and anti-starvation rules."""

    def __init__(
        self,
        qm: Optional[QueueManager] = None,
        aging_threshold_sec: float = DEFAULT_AGING_THRESHOLD_SEC,
    ) -> None:
        self.queue_manager = qm or queue_manager
        self.aging_threshold_sec = max(0.01, float(aging_threshold_sec))
        self.stats = AgingStats()

    def check_and_promote_aged_event(
        self,
        now: Optional[float] = None,
    ) -> Optional[Event]:
        """Inspect the head of BEST_EFFORT queue.
        
        If head age > aging_threshold_sec and event is stateless, promote to NORMAL and return it.
        Otherwise, returns None without removing anything from queues.
        """
        current_time = now if now is not None else time.time()
        best_effort_queue = self.queue_manager.best_effort_queue

        # 1. Non-destructively peek at the head of the BEST_EFFORT queue
        head_event = best_effort_queue.peek()
        if head_event is None:
            return None

        self.stats.evaluated_count += 1
        ref_time = head_event.received_at if head_event.received_at is not None else head_event.timestamp
        wait_time = max(0.0, current_time - ref_time)

        # 2. Check aging threshold
        if wait_time <= self.aging_threshold_sec:
            self.stats.skipped_not_expired_count += 1
            return None

        # 3. SAFETY RULE: Restrict priority aging strictly to stateless event types
        if not is_stateless_event(head_event):
            self.stats.skipped_stateful_count += 1
            return None

        # 4. Promote and pop the aged item
        try:
            event = best_effort_queue.dequeue_nowait()
        except QueueEmpty:
            return None

        # Update event priority and attach promotion metadata
        event.priority = Priority.NORMAL
        event.payload["_aged_from"] = Priority.BEST_EFFORT.value
        event.payload["_promoted_at"] = current_time
        event.payload["_aging_wait_time"] = round(wait_time, 4)

        if hasattr(event, "attach_audit"):
            event.attach_audit(
                rule_id="rule-priority-aging-promoted",
                score=round(wait_time * 10.0, 2),
                evaluated_at=current_time,
                features={
                    "original_priority": Priority.BEST_EFFORT.value,
                    "promoted_to": Priority.NORMAL.value,
                    "wait_time_sec": round(wait_time, 4),
                    "aging_threshold_sec": self.aging_threshold_sec,
                    "event_type": event.event_type,
                    "is_stateless": True,
                },
            )

        self.stats.promoted_count += 1
        self.stats.last_promoted_at = current_time
        return event

    async def pop_normal(
        self,
        timeout: Optional[float] = None,
        now: Optional[float] = None,
    ) -> Event:
        """Pull next task for the NORMAL processing lane with Lazy Priority Aging.
        
        Checks if the head of BEST_EFFORT has starved (> threshold). If so, promotes
        and returns it first. Otherwise, pulls from the NORMAL queue.
        """
        promoted = self.check_and_promote_aged_event(now=now)
        if promoted is not None:
            return promoted

        if timeout is not None:
            return await asyncio.wait_for(self.queue_manager.normal_queue.dequeue(), timeout=timeout)
        return await self.queue_manager.normal_queue.dequeue()

    def pop_normal_nowait(self, now: Optional[float] = None) -> Event:
        """Immediately pull next task for NORMAL lane or raise asyncio.QueueEmpty."""
        promoted = self.check_and_promote_aged_event(now=now)
        if promoted is not None:
            return promoted
        return self.queue_manager.normal_queue.dequeue_nowait()

    async def pop_critical(self, timeout: Optional[float] = None) -> Event:
        """Pull strictly from CRITICAL queue (never subject to aging, zero shedding)."""
        if timeout is not None:
            return await asyncio.wait_for(self.queue_manager.critical_queue.dequeue(), timeout=timeout)
        return await self.queue_manager.critical_queue.dequeue()

    def pop_critical_nowait(self) -> Event:
        """Immediately pull from CRITICAL queue or raise asyncio.QueueEmpty."""
        return self.queue_manager.critical_queue.dequeue_nowait()

    async def pop_best_effort(self, timeout: Optional[float] = None) -> Event:
        """Pull directly from BEST_EFFORT queue."""
        if timeout is not None:
            return await asyncio.wait_for(self.queue_manager.best_effort_queue.dequeue(), timeout=timeout)
        return await self.queue_manager.best_effort_queue.dequeue()

    def pop_best_effort_nowait(self) -> Event:
        """Immediately pull from BEST_EFFORT queue or raise asyncio.QueueEmpty."""
        return self.queue_manager.best_effort_queue.dequeue_nowait()

    async def pop_any(self, now: Optional[float] = None) -> Optional[Event]:
        """Pull highest priority available event: CRITICAL -> NORMAL (with aging) -> BEST_EFFORT."""
        current_time = now if now is not None else time.time()

        # 1. CRITICAL has strict first priority
        if not self.queue_manager.critical_queue.is_empty():
            return self.queue_manager.critical_queue.dequeue_nowait()

        # 2. Check Lazy Priority Aging for BEST_EFFORT before NORMAL
        promoted = self.check_and_promote_aged_event(now=current_time)
        if promoted is not None:
            return promoted

        # 3. NORMAL queue
        if not self.queue_manager.normal_queue.is_empty():
            return self.queue_manager.normal_queue.dequeue_nowait()

        # 4. BEST_EFFORT queue
        if not self.queue_manager.best_effort_queue.is_empty():
            return self.queue_manager.best_effort_queue.dequeue_nowait()

        return None


DEFAULT_EMA_WINDOW_SEC: float = 3.0
DEFAULT_EMA_SAMPLE_INTERVAL_SEC: float = 0.5
# alpha = 2 / ((window / sample_interval) + 1) = 2 / ((3.0 / 0.5) + 1) = 2 / 7 ≈ 0.2857
DEFAULT_EMA_ALPHA: float = 0.2857
DEFAULT_SLA_DEPTH_THRESHOLD: float = 20.0
DEFAULT_SCALE_DOWN_COOLDOWN_SEC: float = 5.0

# Base and Surge allocations (total = 8 workers)
DEFAULT_BASE_ALLOCATION: Dict[Priority, int] = {
    Priority.CRITICAL: 2,
    Priority.NORMAL: 4,
    Priority.BEST_EFFORT: 2,
}
# Shift workers from BEST_EFFORT and NORMAL strictly to CRITICAL
DEFAULT_SURGE_ALLOCATION: Dict[Priority, int] = {
    Priority.CRITICAL: 6,
    Priority.NORMAL: 1,
    Priority.BEST_EFFORT: 1,
}


class QueueLagAutoScaler:
    """Monitors Critical queue lag using Exponential Moving Average (EMA) and manages dynamic worker reallocation.
    
    Formula:
        EMA_t = alpha * Depth_t + (1 - alpha) * EMA_{t-1}
        
    Dynamic Reallocation:
        When Critical queue EMA breaches SLA threshold, dynamically shifts worker threads
        from BEST_EFFORT and NORMAL lanes strictly to CRITICAL.
        
    Anti-Thrashing Cooldown:
        Enforces a 5.0-second scale-down cooldown timer to eliminate worker flapping when traffic
        oscillates around the threshold.
    """

    def __init__(
        self,
        qm: Optional[QueueManager] = None,
        wp: Optional[Any] = None,
        sla_threshold: float = DEFAULT_SLA_DEPTH_THRESHOLD,
        alpha: float = DEFAULT_EMA_ALPHA,
        cooldown_sec: float = DEFAULT_SCALE_DOWN_COOLDOWN_SEC,
        base_allocation: Optional[Dict[Priority, int]] = None,
        surge_allocation: Optional[Dict[Priority, int]] = None,
    ) -> None:
        self.queue_manager = qm or queue_manager
        self._worker_pool = wp
        self.sla_threshold = float(sla_threshold)
        self.alpha = float(alpha)
        self.cooldown_sec = float(cooldown_sec)
        self.base_allocation = dict(base_allocation or DEFAULT_BASE_ALLOCATION)
        self.surge_allocation = dict(surge_allocation or DEFAULT_SURGE_ALLOCATION)

        self.current_ema: float = 0.0
        self._ema_initialized: bool = False
        self.is_scaled_up: bool = False
        self.last_scale_up_time: Optional[float] = None
        self.last_scale_down_time: Optional[float] = None
        self.total_scale_ups: int = 0
        self.total_scale_downs: int = 0

        self._monitor_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    @property
    def worker_pool(self) -> Any:
        if self._worker_pool is None:
            from pipeline.workers.worker_pool import worker_pool
            self._worker_pool = worker_pool
        return self._worker_pool

    def update_ema(self, current_depth: float) -> float:
        """Compute the next EMA value using: EMA_t = alpha * Depth_t + (1 - alpha) * EMA_{t-1}."""
        val = max(0.0, float(current_depth))
        if not self._ema_initialized:
            self.current_ema = val
            self._ema_initialized = True
        else:
            self.current_ema = (self.alpha * val) + ((1.0 - self.alpha) * self.current_ema)
        return round(self.current_ema, 4)

    def reset_ema(self) -> None:
        """Reset EMA tracking state."""
        self.current_ema = 0.0
        self._ema_initialized = False

    async def evaluate_scaling(
        self,
        now: Optional[float] = None,
        critical_depth: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Check Critical queue EMA against SLA threshold and execute scale-up or cooldown scale-down."""
        t = now if now is not None else time.time()
        depth = critical_depth if critical_depth is not None else self.queue_manager.critical_queue.depth()
        ema = self.update_ema(depth)

        action_taken = "NONE"

        if ema >= self.sla_threshold:
            # Breach SLA threshold: scale up CRITICAL lane if not already scaled up
            if not self.is_scaled_up:
                await self.worker_pool.set_allocation(self.surge_allocation)
                self.is_scaled_up = True
                self.last_scale_up_time = t
                self.total_scale_ups += 1
                action_taken = "SCALE_UP"
        else:
            # Below SLA threshold: check anti-thrashing cooldown timer
            if self.is_scaled_up:
                time_since_scale_up = t - (self.last_scale_up_time or 0.0)
                if time_since_scale_up >= self.cooldown_sec:
                    # Cooldown satisfied -> scale down to base allocation
                    await self.worker_pool.set_allocation(self.base_allocation)
                    self.is_scaled_up = False
                    self.last_scale_down_time = t
                    self.total_scale_downs += 1
                    action_taken = "SCALE_DOWN"
                else:
                    action_taken = "COOLDOWN_ACTIVE"

        return {
            "ema": ema,
            "depth": depth,
            "is_scaled_up": self.is_scaled_up,
            "action": action_taken,
            "timestamp": t,
            "current_allocation": self.worker_pool.get_allocation() if hasattr(self.worker_pool, "get_allocation") else {},
        }

    async def _monitor_loop(self, sample_interval: float = DEFAULT_EMA_SAMPLE_INTERVAL_SEC) -> None:
        """Background loop continuously updating EMA and enforcing auto-scaling."""
        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(sample_interval)
                if self._stop_event.is_set():
                    break
                await self.evaluate_scaling()
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    def start_monitor(self, sample_interval: float = DEFAULT_EMA_SAMPLE_INTERVAL_SEC) -> None:
        """Launch background auto-scaler monitor."""
        if self._monitor_task is not None and not self._monitor_task.done():
            return
        self._stop_event.clear()
        self._monitor_task = asyncio.create_task(
            self._monitor_loop(sample_interval=sample_interval),
            name="queue-lag-autoscaler-monitor",
        )

    async def stop_monitor(self, timeout: float = 1.0) -> None:
        """Stop background auto-scaler monitor."""
        self._stop_event.set()
        if self._monitor_task is not None and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await asyncio.wait_for(self._monitor_task, timeout=timeout)
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                pass
        self._monitor_task = None


# Default singleton instances
dispatcher = Dispatcher()
queue_lag_autoscaler = QueueLagAutoScaler()

__all__ = [
    "Dispatcher",
    "dispatcher",
    "AgingStats",
    "STATELESS_EVENT_TYPES",
    "STATEFUL_EVENT_TYPES",
    "DEFAULT_AGING_THRESHOLD_SEC",
    "is_stateless_event",
    "is_stateful_event",
    "QueueLagAutoScaler",
    "queue_lag_autoscaler",
    "DEFAULT_EMA_WINDOW_SEC",
    "DEFAULT_EMA_SAMPLE_INTERVAL_SEC",
    "DEFAULT_EMA_ALPHA",
    "DEFAULT_SLA_DEPTH_THRESHOLD",
    "DEFAULT_SCALE_DOWN_COOLDOWN_SEC",
    "DEFAULT_BASE_ALLOCATION",
    "DEFAULT_SURGE_ALLOCATION",
]

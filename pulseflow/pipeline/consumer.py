"""PulseFlow pipeline: Consumer & In-Flight ACK Tracker.

Provides fault tolerance, in-flight event tracking, timeout auto-recovery, and manual ACKs.
Guarantees zero-loss processing (critical_events_lost == 0) even under worker failures or crashes.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from contracts.events import Event
from contracts.priorities import Priority
from pipeline.audit import audit_logger
from pipeline.queues.queue_manager import QueueManager, queue_manager

logger = logging.getLogger("pulseflow.consumer")

DEFAULT_IN_FLIGHT_TIMEOUT_SEC: float = 3.0
DEFAULT_CHECK_INTERVAL_SEC: float = 1.0


class InFlightTracker:
    """Tracks currently processing events and handles timeout auto-recovery.
    
    Structure:
        _in_flight: {event_id: (event, start_timestamp)}
    """

    def __init__(
        self,
        qm: Optional[QueueManager] = None,
        timeout_sec: float = DEFAULT_IN_FLIGHT_TIMEOUT_SEC,
        check_interval_sec: float = DEFAULT_CHECK_INTERVAL_SEC,
    ) -> None:
        self.queue_manager = qm or queue_manager
        self.timeout_sec = max(0.1, float(timeout_sec))
        self.check_interval_sec = max(0.05, float(check_interval_sec))

        self._in_flight: Dict[str, Tuple[Event, float]] = {}
        self._lock: Optional[asyncio.Lock] = None
        self._monitor_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

        # Telemetry metrics
        self.total_tracked: int = 0
        self.total_acked: int = 0
        self.total_recovered: int = 0
        self.total_timeouts: int = 0

    def _get_lock(self) -> asyncio.Lock:
        try:
            current_loop = asyncio.get_running_loop()
            if self._lock is not None:
                lock_loop = getattr(self._lock, "_loop", None)
                if lock_loop is not None and (lock_loop.is_closed() or lock_loop is not current_loop):
                    self._lock = None
        except RuntimeError:
            pass
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    @property
    def in_flight_count(self) -> int:
        """Current number of active, un-ACKed events."""
        return len(self._in_flight)

    @property
    def is_monitor_running(self) -> bool:
        return self._monitor_task is not None and not self._monitor_task.done()

    def track(self, event: Event, now: Optional[float] = None) -> None:
        """Register an event in the in-flight buffer when pulled by a worker."""
        t = now if now is not None else time.time()
        self._in_flight[event.event_id] = (event, t)
        self.total_tracked += 1

    def ack(self, event_id: str) -> bool:
        """Evict an event from the in-flight buffer upon explicit worker ACK.
        
        Returns True if the event was present and removed, False otherwise.
        """
        if event_id in self._in_flight:
            del self._in_flight[event_id]
            self.total_acked += 1
            return True
        return False

    def nack(self, event_id: str, requeue: bool = True) -> Optional[Event]:
        """Negative-acknowledgement: remove from in-flight and optionally re-queue immediately."""
        if event_id in self._in_flight:
            event, _ = self._in_flight.pop(event_id)
            if requeue:
                event.ensure_priority()
                # Requeue to CRITICAL queue to guarantee zero-loss
                self.queue_manager.critical_queue.enqueue_nowait(event)
                self.total_recovered += 1
            return event
        return None

    def get_in_flight(self, event_id: str) -> Optional[Tuple[Event, float]]:
        """Return (event, timestamp) tuple if event is currently in-flight."""
        return self._in_flight.get(event_id)

    def is_in_flight(self, event_id: str) -> bool:
        """True if event is currently active and un-ACKed."""
        return event_id in self._in_flight

    def get_all_in_flight(self) -> Dict[str, Tuple[Event, float]]:
        """Return shallow copy of all active in-flight records."""
        return dict(self._in_flight)

    async def check_and_recover_timeouts(self, now: Optional[float] = None) -> List[Event]:
        """Scan in-flight buffer for items exceeding timeout_sec without an ACK.
        
        Removes timed-out items from in_flight and automatically returns them to the
        CRITICAL queue for retry, preserving the zero-loss critical invariant.
        """
        current_time = now if now is not None else time.time()
        timed_out_ids: List[str] = []

        async with self._get_lock():
            for event_id, (event, start_time) in list(self._in_flight.items()):
                elapsed = current_time - start_time
                if elapsed > self.timeout_sec:
                    timed_out_ids.append(event_id)

            recovered_events: List[Event] = []
            for event_id in timed_out_ids:
                if event_id in self._in_flight:
                    event, start_time = self._in_flight.pop(event_id)
                    self.total_timeouts += 1
                    self.total_recovered += 1

                    # Mark retry lineage in event payload
                    event.payload["_retry_count"] = event.payload.get("_retry_count", 0) + 1
                    event.payload["_recovered_at"] = current_time
                    event.payload["_timeout_elapsed_sec"] = round(current_time - start_time, 4)

                    # Hard Invariant: Recover un-ACKed items directly to CRITICAL queue
                    event.priority = Priority.CRITICAL
                    self.queue_manager.critical_queue.enqueue_nowait(event)
                    recovered_events.append(event)

                    logger.warning(
                        "In-flight event timeout: %s (type=%s, elapsed=%.2fs). Re-queued to CRITICAL.",
                        event_id,
                        event.event_type,
                        current_time - start_time,
                    )

        # Log audit record if audit logger is running
        for rev_event in recovered_events:
            if hasattr(rev_event, "attach_audit"):
                rev_event.attach_audit(
                    rule_id="rule-timeout-recovery",
                    score=999.0,
                    evaluated_at=current_time,
                    features={
                        "action": "REQUEUE_CRITICAL",
                        "retry_count": rev_event.payload.get("_retry_count", 1),
                    },
                )
                try:
                    audit_logger.log_event_nowait(rev_event)
                except Exception:
                    pass

        return recovered_events

    async def _monitor_loop(self) -> None:
        """Background loop continuously scanning for un-ACKed timed-out events."""
        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(self.check_interval_sec)
                if self._stop_event.is_set():
                    break
                await self.check_and_recover_timeouts()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in in-flight timeout monitor loop: %s", e)

    def _is_monitor_alive(self) -> bool:
        """Check if background monitor task is alive and on current running loop."""
        if self._monitor_task is None or self._monitor_task.done():
            return False
        try:
            current_loop = asyncio.get_running_loop()
            task_loop = getattr(self._monitor_task, "_loop", None)
            if task_loop is not None and (task_loop.is_closed() or task_loop is not current_loop):
                return False
        except RuntimeError:
            return False
        return True

    def start_monitor(self) -> None:
        """Launch the background timeout check monitor."""
        if self._is_monitor_alive():
            return
        self._stop_event = asyncio.Event()
        self._monitor_task = asyncio.create_task(
            self._monitor_loop(),
            name="in-flight-timeout-monitor",
        )

    async def stop_monitor(self, timeout: float = 1.0) -> None:
        """Stop background timeout monitor."""
        self._stop_event.set()
        if self._monitor_task is not None and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await asyncio.wait_for(self._monitor_task, timeout=timeout)
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                pass
        self._monitor_task = None

    def clear(self) -> int:
        """Clear all in-flight tracking (useful in test tear-down)."""
        count = len(self._in_flight)
        self._in_flight.clear()
        return count


# Global singleton instance
in_flight_tracker = InFlightTracker()


# Public functional helpers
def track_event(event: Event, now: Optional[float] = None) -> None:
    """Helper to place an event in the in-flight buffer."""
    in_flight_tracker.track(event, now=now)


def ack_event(event_id: str) -> bool:
    """Helper to acknowledge and remove an event from the in-flight buffer."""
    return in_flight_tracker.ack(event_id)


def nack_event(event_id: str, requeue: bool = True) -> Optional[Event]:
    """Helper to negatively acknowledge an event."""
    return in_flight_tracker.nack(event_id, requeue=requeue)


__all__ = [
    "InFlightTracker",
    "in_flight_tracker",
    "track_event",
    "ack_event",
    "nack_event",
    "DEFAULT_IN_FLIGHT_TIMEOUT_SEC",
    "DEFAULT_CHECK_INTERVAL_SEC",
]

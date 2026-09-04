"""PulseFlow pipeline: Processing Telemetry Tracker.

Provides sliding-window telemetry for actual event processing throughput (events/sec)
and end-to-end processing latency (ms), measured from event ingestion acceptance
(received_at) to successful persistence.
"""

import time
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

from contracts.priorities import Priority


class ProcessingTelemetryTracker:
    """Sliding-window runtime telemetry tracker for processed events and latency."""

    def __init__(self, window_sec: float = 5.0, max_recent: int = 1000) -> None:
        """Initialize the telemetry tracker.

        Args:
            window_sec: Time duration (seconds) of the sliding window for rate and latency.
            max_recent: Maximum count of recent latency values to retain for percentiles.
        """
        self.window_sec = float(window_sec)
        self.max_recent = max_recent
        self.reset()

    def reset(self) -> None:
        """Reset all counters and rolling windows to initial state."""
        self._total_processed: int = 0
        # Window samples: deque of (timestamp, count, sum_latency_ms, priority)
        self._window_samples: Deque[Tuple[float, int, float, Optional[Priority]]] = deque()
        self._recent_latencies: Deque[float] = deque(maxlen=self.max_recent)
        self._lane_latencies: Dict[Priority, Deque[float]] = {
            p: deque(maxlen=self.max_recent) for p in Priority
        }

    def record(
        self,
        latency_ms: float,
        priority: Optional[Priority] = None,
        now: Optional[float] = None,
    ) -> None:
        """Record a single processed event with its end-to-end latency."""
        t = now if now is not None else time.time()
        lat = max(0.0, float(latency_ms))
        self._total_processed += 1
        self._window_samples.append((t, 1, lat, priority))
        self._recent_latencies.append(lat)
        if priority in self._lane_latencies:
            self._lane_latencies[priority].append(lat)
        self._prune(t)

    def record_batch(
        self,
        latencies: List[float],
        priority: Optional[Priority] = None,
        now: Optional[float] = None,
    ) -> None:
        """Record a batch of processed events with their respective latencies."""
        if not latencies:
            return
        t = now if now is not None else time.time()
        clean_lats = [max(0.0, float(lat)) for lat in latencies]
        count = len(clean_lats)
        total_lat = sum(clean_lats)

        self._total_processed += count
        self._window_samples.append((t, count, total_lat, priority))
        self._recent_latencies.extend(clean_lats)
        if priority in self._lane_latencies:
            self._lane_latencies[priority].extend(clean_lats)
        self._prune(t)

    def _prune(self, current_time: float) -> None:
        """Prune samples outside the active sliding time window."""
        cutoff = current_time - self.window_sec
        while self._window_samples and self._window_samples[0][0] < cutoff:
            self._window_samples.popleft()

    def get_processing_rate(self, now: Optional[float] = None) -> float:
        """Calculate processing throughput (events/sec) over the active sliding window."""
        t = now if now is not None else time.time()
        self._prune(t)
        if not self._window_samples:
            return 0.0

        total_count = sum(s[1] for s in self._window_samples)
        earliest = self._window_samples[0][0]
        elapsed = t - earliest
        effective_window = max(1.0, min(self.window_sec, elapsed))
        return round(total_count / effective_window, 2)

    def get_avg_latency_ms(
        self,
        priority: Optional[Priority] = None,
        now: Optional[float] = None,
    ) -> float:
        """Return average processing latency in milliseconds over the sliding window."""
        t = now if now is not None else time.time()
        self._prune(t)

        if priority is not None:
            lane_samples = [s for s in self._window_samples if s[3] == priority]
            if lane_samples:
                count = sum(s[1] for s in lane_samples)
                total = sum(s[2] for s in lane_samples)
                return round(total / count, 2) if count > 0 else 0.0
            # Fallback to recent history for lane if window has no active events
            recent = self._lane_latencies.get(priority)
            return round(sum(recent) / len(recent), 2) if recent else 0.0

        if self._window_samples:
            count = sum(s[1] for s in self._window_samples)
            total = sum(s[2] for s in self._window_samples)
            return round(total / count, 2) if count > 0 else 0.0

        # Fallback to recent latencies if window is currently empty
        if self._recent_latencies:
            return round(sum(self._recent_latencies) / len(self._recent_latencies), 2)
        return 0.0

    def get_percentiles(self) -> Tuple[float, float]:
        """Return (p95, p99) processing latency in milliseconds."""
        if not self._recent_latencies:
            return 0.0, 0.0
        sorted_lats = sorted(self._recent_latencies)
        n = len(sorted_lats)
        p95 = sorted_lats[min(int(0.95 * n), n - 1)]
        p99 = sorted_lats[min(int(0.99 * n), n - 1)]
        return round(p95, 2), round(p99, 2)

    def get_processed_count(self) -> int:
        """Return total cumulative count of events processed since startup/reset."""
        return self._total_processed


# Shared global processing telemetry tracker
processing_telemetry = ProcessingTelemetryTracker()

__all__ = ["ProcessingTelemetryTracker", "processing_telemetry"]

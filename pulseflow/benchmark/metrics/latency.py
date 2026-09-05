"""PulseFlow benchmark: Latency Analyzer.

Analyzes end-to-end processing latency for benchmark runs.
Computes:
  - Average (mean), P50 (median), P90, P95, and P99 latencies in milliseconds.
  - Strict breakdown by Priority tier (CRITICAL, NORMAL, BEST_EFFORT) so that critical
    latencies (orders/payments) are never obscured by bulk non-critical traffic.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping, Optional

from contracts.priorities import Priority


def calculate_percentile(values: list[float], percentile: float) -> float:
    """Calculate the given percentile (0.0 - 100.0) from a list of numerical values."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * (percentile / 100.0)
    floor_idx = int(k)
    ceil_idx = min(floor_idx + 1, len(sorted_vals) - 1)
    weight = k - floor_idx
    return round(sorted_vals[floor_idx] + weight * (sorted_vals[ceil_idx] - sorted_vals[floor_idx]), 2)


@dataclass
class LatencyStats:
    """Statistical summary of latencies in milliseconds."""
    sample_count: int = 0
    avg_ms: float = 0.0
    p50_ms: float = 0.0
    p90_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    p100_ms: float = 0.0
    max_ms: float = 0.0
    min_ms: float = 0.0

    @classmethod
    def from_samples(cls, samples: list[float]) -> "LatencyStats":
        if not samples:
            return cls()
        max_val = round(max(samples), 2)
        return cls(
            sample_count=len(samples),
            avg_ms=round(sum(samples) / len(samples), 2),
            p50_ms=calculate_percentile(samples, 50),
            p90_ms=calculate_percentile(samples, 90),
            p95_ms=calculate_percentile(samples, 95),
            p99_ms=calculate_percentile(samples, 99),
            p100_ms=max_val,
            max_ms=max_val,
            min_ms=round(min(samples), 2),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TieredLatencyReport:
    """Tier-wise and overall latency report."""
    overall: LatencyStats
    critical: LatencyStats
    normal: LatencyStats
    best_effort: LatencyStats

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall": self.overall.to_dict(),
            "critical": self.critical.to_dict(),
            "normal": self.normal.to_dict(),
            "best_effort": self.best_effort.to_dict(),
        }


def analyze_latencies(
    latencies_by_priority: Mapping[Priority | str, list[float]],
) -> TieredLatencyReport:
    """Analyze raw latency samples collected per priority lane into a structured report."""
    crit_samples: list[float] = []
    norm_samples: list[float] = []
    best_samples: list[float] = []

    for key, values in latencies_by_priority.items():
        if isinstance(key, Priority):
            p = key
        else:
            p = Priority.from_str(str(key))

        if p == Priority.CRITICAL:
            crit_samples.extend(values)
        elif p == Priority.NORMAL:
            norm_samples.extend(values)
        elif p == Priority.BEST_EFFORT:
            best_samples.extend(values)

    all_samples = crit_samples + norm_samples + best_samples

    return TieredLatencyReport(
        overall=LatencyStats.from_samples(all_samples),
        critical=LatencyStats.from_samples(crit_samples),
        normal=LatencyStats.from_samples(norm_samples),
        best_effort=LatencyStats.from_samples(best_samples),
    )


def extract_latency_summary_from_telemetry(telemetry: dict[str, Any]) -> dict[str, Any]:
    """Helper to format or extract tier-wise latency stats from runner output dictionaries."""
    return {
        "pipeline": telemetry.get("pipeline_type", "UNKNOWN"),
        "overall": telemetry.get("overall_latency_ms", {}),
        "critical": telemetry.get("critical_latency_ms", {}),
        "normal": telemetry.get("normal_latency_ms", {}),
        "best_effort": telemetry.get("best_effort_latency_ms", {}),
    }

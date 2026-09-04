"""PulseFlow benchmark: Throughput Analyzer.

Analyzes processing and ingestion throughput across benchmark executions.
Computes:
  - Overall events processed per second.
  - Per-phase throughput (Normal load phase, Spike surge phase, Recovery phase).
  - Processing rate vs Ingestion rate ratio (processing efficiency).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional


@dataclass
class PhaseThroughput:
    """Throughput statistics for a distinct phase of the workload."""
    phase_name: str
    events_ingested: int = 0
    events_processed: int = 0
    duration_sec: float = 0.0
    throughput_events_per_sec: float = 0.0
    completion_ratio: float = 1.0

    @classmethod
    def calculate(
        cls,
        phase_name: str,
        events_ingested: int,
        events_processed: int,
        duration_sec: float,
    ) -> "PhaseThroughput":
        rate = (events_processed / duration_sec) if duration_sec > 0 else 0.0
        ratio = (events_processed / events_ingested) if events_ingested > 0 else 1.0
        return cls(
            phase_name=phase_name,
            events_ingested=events_ingested,
            events_processed=events_processed,
            duration_sec=round(duration_sec, 3),
            throughput_events_per_sec=round(rate, 2),
            completion_ratio=round(ratio, 4),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OverallThroughputReport:
    """Consolidated throughput evaluation."""
    total_duration_sec: float
    total_ingested: int
    total_processed: int
    overall_throughput_events_per_sec: float
    peak_throughput_events_per_sec: float
    phases: dict[str, PhaseThroughput]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_duration_sec": self.total_duration_sec,
            "total_ingested": self.total_ingested,
            "total_processed": self.total_processed,
            "overall_throughput_events_per_sec": self.overall_throughput_events_per_sec,
            "peak_throughput_events_per_sec": self.peak_throughput_events_per_sec,
            "phases": {name: p.to_dict() for name, p in self.phases.items()},
        }


def compute_overall_throughput(
    total_processed: int,
    total_duration_sec: float,
    total_ingested: Optional[int] = None,
) -> float:
    """Compute basic overall events per second."""
    if total_duration_sec <= 0:
        return 0.0
    return round(total_processed / total_duration_sec, 2)


def analyze_throughput_from_telemetry(telemetry: dict[str, Any]) -> dict[str, Any]:
    """Extract and format throughput report from runner output dictionary."""
    total_processed = telemetry.get("total_processed", 0)
    total_duration_sec = telemetry.get("total_duration_sec", 0.0)
    total_ingested = telemetry.get("total_ingested", total_processed)

    rate = compute_overall_throughput(total_processed, total_duration_sec, total_ingested)

    return {
        "pipeline_type": telemetry.get("pipeline_type", "UNKNOWN"),
        "total_ingested": total_ingested,
        "total_processed": total_processed,
        "total_duration_sec": total_duration_sec,
        "throughput_events_per_sec": rate,
    }

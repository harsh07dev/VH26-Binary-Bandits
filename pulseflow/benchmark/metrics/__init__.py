"""PulseFlow benchmark: Metrics Analysis Package.

Exports analyzers for:
  - Latency (tiered percentiles & averages)
  - Throughput (overall & per-phase)
  - Reliability (critical event preservation & controlled shedding)
"""

from benchmark.metrics.latency import (
    LatencyStats,
    TieredLatencyReport,
    analyze_latencies,
    calculate_percentile,
    extract_latency_summary_from_telemetry,
)
from benchmark.metrics.throughput import (
    PhaseThroughput,
    OverallThroughputReport,
    compute_overall_throughput,
    analyze_throughput_from_telemetry,
)
from benchmark.metrics.reliability import (
    TierReliabilityStats,
    ReliabilityReport,
    analyze_reliability,
)

__all__ = [
    # Latency
    "LatencyStats",
    "TieredLatencyReport",
    "analyze_latencies",
    "calculate_percentile",
    "extract_latency_summary_from_telemetry",
    # Throughput
    "PhaseThroughput",
    "OverallThroughputReport",
    "compute_overall_throughput",
    "analyze_throughput_from_telemetry",
    # Reliability
    "TierReliabilityStats",
    "ReliabilityReport",
    "analyze_reliability",
]

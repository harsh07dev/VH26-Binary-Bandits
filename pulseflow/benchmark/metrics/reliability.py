"""PulseFlow benchmark: Reliability & Load Shedding Analyzer.

Evaluates data integrity, zero critical loss invariants, and controlled shedding:
  - Critical Events Lost (MUST BE 0 for PulseFlow; often > 0 for naive FIFO under surge).
  - Shed Non-Critical Events (intentional drop of best-effort traffic under backpressure).
  - Sampled Non-Critical Events.
  - Deferred Normal Events.
  - Data Retention Ratios by tier.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from contracts.priorities import Priority


@dataclass
class TierReliabilityStats:
    """Reliability statistics for an individual priority tier."""
    priority: str
    ingested_count: int
    processed_count: int
    lost_count: int
    shed_count: int = 0
    sampled_count: int = 0
    deferred_count: int = 0
    delivery_rate: float = 1.0

    @classmethod
    def create(
        cls,
        priority: str,
        ingested: int,
        processed: int,
        lost: int,
        shed: int = 0,
        sampled: int = 0,
        deferred: int = 0,
    ) -> "TierReliabilityStats":
        delivery = (processed / ingested) if ingested > 0 else 1.0
        return cls(
            priority=priority,
            ingested_count=ingested,
            processed_count=processed,
            lost_count=lost,
            shed_count=shed,
            sampled_count=sampled,
            deferred_count=deferred,
            delivery_rate=round(delivery, 4),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReliabilityReport:
    """Consolidated reliability evaluation across all priority tiers."""
    pipeline_type: str
    critical_events_lost: int
    non_critical_events_shed: int
    events_deferred: int
    events_sampled: int
    critical_delivery_rate: float
    overall_delivery_rate: float
    is_critical_invariant_preserved: bool
    tier_breakdown: dict[str, TierReliabilityStats]

    def to_dict(self) -> dict[str, Any]:
        return {
            "pipeline_type": self.pipeline_type,
            "critical_events_lost": self.critical_events_lost,
            "non_critical_events_shed": self.non_critical_events_shed,
            "events_deferred": self.events_deferred,
            "events_sampled": self.events_sampled,
            "critical_delivery_rate": self.critical_delivery_rate,
            "overall_delivery_rate": self.overall_delivery_rate,
            "is_critical_invariant_preserved": self.is_critical_invariant_preserved,
            "tier_breakdown": {k: v.to_dict() for k, v in self.tier_breakdown.items()},
        }


def analyze_reliability(telemetry: Mapping[str, Any]) -> ReliabilityReport:
    """Analyze reliability metrics from runner telemetry conforming to contracts.metrics.SystemSnapshot."""
    pipeline_type = str(telemetry.get("pipeline_type", "UNKNOWN"))
    crit_lost = int(telemetry.get("critical_events_lost", 0))
    norm_lost = int(telemetry.get("normal_events_lost", 0))
    best_lost = int(telemetry.get("best_effort_events_lost", 0))

    events_shed = int(telemetry.get("events_shed", telemetry.get("total_dropped", 0)))
    events_deferred = int(telemetry.get("events_deferred", 0))
    events_sampled = int(telemetry.get("events_sampled", 0))

    processed_by_priority = telemetry.get("processed_by_priority", {})
    crit_proc = processed_by_priority.get(Priority.CRITICAL.value, 0)
    norm_proc = processed_by_priority.get(Priority.NORMAL.value, 0)
    best_proc = processed_by_priority.get(Priority.BEST_EFFORT.value, 0)

    crit_ingested = crit_proc + crit_lost
    norm_ingested = norm_proc + norm_lost + events_deferred
    best_ingested = best_proc + best_lost

    total_ingested = crit_ingested + norm_ingested + best_ingested
    total_processed = crit_proc + norm_proc + best_proc

    crit_delivery = (crit_proc / crit_ingested) if crit_ingested > 0 else 1.0
    overall_delivery = (total_processed / total_ingested) if total_ingested > 0 else 1.0

    # Invariant: PulseFlow must NEVER lose critical events!
    is_critical_invariant_preserved = (crit_lost == 0)

    tier_stats = {
        Priority.CRITICAL.value: TierReliabilityStats.create(
            priority=Priority.CRITICAL.value,
            ingested=crit_ingested,
            processed=crit_proc,
            lost=crit_lost,
            shed=0,
            sampled=0,
            deferred=0,
        ),
        Priority.NORMAL.value: TierReliabilityStats.create(
            priority=Priority.NORMAL.value,
            ingested=norm_ingested,
            processed=norm_proc,
            lost=norm_lost,
            shed=0,
            sampled=0,
            deferred=events_deferred,
        ),
        Priority.BEST_EFFORT.value: TierReliabilityStats.create(
            priority=Priority.BEST_EFFORT.value,
            ingested=best_ingested,
            processed=best_proc,
            lost=best_lost,
            shed=events_shed,
            sampled=events_sampled,
            deferred=0,
        ),
    }

    return ReliabilityReport(
        pipeline_type=pipeline_type,
        critical_events_lost=crit_lost,
        non_critical_events_shed=events_shed,
        events_deferred=events_deferred,
        events_sampled=events_sampled,
        critical_delivery_rate=round(crit_delivery, 4),
        overall_delivery_rate=round(overall_delivery, 4),
        is_critical_invariant_preserved=is_critical_invariant_preserved,
        tier_breakdown=tier_stats,
    )

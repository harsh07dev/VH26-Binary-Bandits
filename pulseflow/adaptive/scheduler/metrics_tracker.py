"""PulseFlow adaptive: Metrics Tracker.

Tracks real-time telemetry from the adaptive decision engine,
including cumulative shedding stats and recent events.
"""
from typing import List, Dict, Any
from collections import deque
from contracts.priorities import Priority
from contracts.actions import Action

class AdaptiveMetricsTracker:
    def __init__(self):
        self.reset()

    def reset(self):
        """Reset all metrics to initial state."""
        self.shed_stats = {
            "shed": 0,
            "deferred": 0,
            "sampled": 0,
            "sampled_kept": 0,
            "sampled_dropped": 0,
            "batched": 0,
            "streamed": 0,
        }
        self.recent_events = deque(maxlen=20)
        self.latest_snapshot = None
        self.latest_decision = None

    def record_decision(self, decision):
        """Record an AdaptiveDecision."""
        self.latest_decision = decision
        
        # Track stats
        if decision.strategy == Action.SHED:
            self.shed_stats["shed"] += 1
        elif decision.strategy == Action.DEFER:
            self.shed_stats["deferred"] += 1
        elif decision.strategy == Action.SAMPLE:
            self.shed_stats["sampled"] += 1
            if getattr(decision, "kept", True):
                self.shed_stats["sampled_kept"] += 1
            else:
                self.shed_stats["sampled_dropped"] += 1
        elif decision.strategy == Action.BATCH:
            self.shed_stats["batched"] += 1
        elif decision.strategy == Action.STREAM:
            self.shed_stats["streamed"] += 1
            
        # Add to recent events
        self.recent_events.append({
            "time": decision.timestamp,
            "id": decision.event_id,
            "type": "EVENT", # Could map from actual event if we pass it
            "tier": decision.priority.value,
            "status": decision.strategy.value,
            "reason": decision.decision_reason
        })

adaptive_metrics = AdaptiveMetricsTracker()

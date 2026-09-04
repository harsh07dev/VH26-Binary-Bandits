"""PulseFlow adaptive: Policy Engine.

Determines the appropriate processing strategy (Action) for a given
Priority lane under a specific PressureState.
"""

import time
from pydantic import BaseModel, Field

from contracts.priorities import Priority
from contracts.actions import Action
from adaptive.pressure.pressure_config import PressureState


class PolicyDecision(BaseModel):
    """Structured decision returned by the Policy Engine."""
    priority: Priority = Field(..., description="The evaluated priority lane")
    pressure: PressureState = Field(..., description="The evaluated system pressure state")
    strategy: Action = Field(..., description="The selected processing action/strategy")
    reason: str = Field(..., description="Explanation for this policy decision")
    timestamp: float = Field(default_factory=time.time, description="Time of decision")


class PolicyEngine:
    """Determines processing strategies based on system pressure and priority."""

    @classmethod
    def decide(cls, priority: Priority, pressure: PressureState) -> PolicyDecision:
        """Evaluate the policy and return a deterministic PolicyDecision."""
        
        if pressure == PressureState.NORMAL:
            # Under normal pressure, all lanes stream
            strategy = Action.STREAM
            reason = f"Normal pressure: {priority.value} lane streams unconditionally."
            
        elif pressure == PressureState.HIGH:
            if priority == Priority.CRITICAL:
                strategy = Action.STREAM
                reason = "High pressure: CRITICAL lane remains streaming."
            elif priority == Priority.NORMAL:
                strategy = Action.BATCH
                reason = "High pressure: NORMAL lane degrades to micro-batching."
            elif priority == Priority.BEST_EFFORT:
                strategy = Action.SAMPLE
                reason = "High pressure: BEST_EFFORT lane degrades to sampling."
                
        elif pressure == PressureState.EXTREME:
            if priority == Priority.CRITICAL:
                strategy = Action.STREAM
                reason = "Extreme pressure: CRITICAL lane is strictly protected and remains streaming."
            elif priority == Priority.NORMAL:
                strategy = Action.DEFER
                reason = "Extreme pressure: NORMAL lane defers processing to shed load."
            elif priority == Priority.BEST_EFFORT:
                strategy = Action.SHED
                reason = "Extreme pressure: BEST_EFFORT lane sheds events entirely."
                
        else:
            # Fallback for unexpected states
            strategy = Action.STREAM if priority == Priority.CRITICAL else Action.DEFER
            reason = f"Unknown pressure state {pressure}, applying safe fallback."
            
        return PolicyDecision(
            priority=priority,
            pressure=pressure,
            strategy=strategy,
            reason=reason
        )

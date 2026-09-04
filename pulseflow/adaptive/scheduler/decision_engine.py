"""PulseFlow adaptive: Decision Engine.

The central orchestration layer of the adaptive intelligence system.
Combines event classification, pressure calculation, policy enforcement,
and worker allocation into a single unified pipeline hook.
"""

import time
from typing import Dict, Optional
from pydantic import BaseModel, Field

from contracts.events import Event
from contracts.priorities import Priority
from contracts.actions import Action
from contracts.metrics import SystemSnapshot
from adaptive.pressure.pressure_config import PressureState

from adaptive.classification.classifier import AdaptiveClassifier
from adaptive.queues.adaptive_queue import AdaptiveQueueRouter
from adaptive.pressure.pressure_calculator import PressureCalculator
from adaptive.policies.policy_engine import PolicyEngine
from adaptive.allocation.worker_allocator import WorkerAllocator
from adaptive.sampling.sampler import ProbabilisticSampler, adaptive_sampler
from pipeline.workers.worker_pool import worker_pool


class AdaptiveDecision(BaseModel):
    """Holistic representation of a single adaptive orchestration cycle."""
    event_id: str = Field(..., description="ID of the processed event")
    priority: Priority = Field(..., description="Classified priority lane")
    pressure_state: PressureState = Field(..., description="Calculated system pressure state")
    pressure_score: float = Field(..., description="Calculated system pressure score (0.0 to 1.0)")
    strategy: Action = Field(..., description="Prescribed processing strategy")
    queue_depth: int = Field(..., description="Total queue depth at time of decision")
    worker_allocation: Dict[Priority, int] = Field(..., description="Desired worker allocation")
    decision_reason: str = Field(..., description="Textual reason for the decision")
    timestamp: float = Field(default_factory=time.time)
    kept: bool = Field(default=True, description="Whether event was kept for processing or dropped")


class DecisionEngine:
    """Orchestrates all adaptive components to make high-level processing decisions."""

    @classmethod
    async def process_event(
        cls,
        event: Event,
        snapshot: SystemSnapshot,
        ingress_rate: float = 0.0,
        sampler: Optional[ProbabilisticSampler] = None,
    ) -> AdaptiveDecision:
        """Run the full adaptive pipeline on a single incoming event."""
        
        # 1. Classification
        classification = AdaptiveClassifier.classify(event)
        
        # 2. System State & Pressure Engine
        pressure = PressureCalculator.calculate(snapshot, ingress_rate)
        
        # 3. Adaptive Policy
        policy = PolicyEngine.decide(classification.assigned_priority, pressure.pressureState)
        
        # 4. Worker Allocation
        allocation = WorkerAllocator.calculate_desired_allocation(pressure.pressureState)
        
        # 5. Execution (Queueing & Reallocation)
        # Determine whether to route event to priority queue:
        # - SHED: completely rejected
        # - SAMPLE: probabilistically kept/dropped by sampler
        # - STREAM / BATCH / DEFER: kept and routed
        kept = True
        if policy.strategy == Action.SHED:
            kept = False
        elif policy.strategy == Action.SAMPLE:
            active_sampler = sampler or adaptive_sampler
            kept = active_sampler.should_keep(event)

        if kept:
            # Reuses our priority router which ensures safety
            await AdaptiveQueueRouter.route_event(event)
            
        # Reallocate workers dynamically (worker_pool safely manages in-flight tasks)
        # Only reallocate if we're actually running (to prevent crashing tests that mock state)
        if worker_pool.is_running:
            await worker_pool.set_allocation(allocation)
            
        return AdaptiveDecision(
            event_id=event.event_id,
            priority=classification.assigned_priority,
            pressure_state=pressure.pressureState,
            pressure_score=pressure.pressureScore,
            strategy=policy.strategy,
            queue_depth=pressure.queueDepth,
            worker_allocation=allocation,
            decision_reason=policy.reason,
            timestamp=time.time(),
            kept=kept,
        )

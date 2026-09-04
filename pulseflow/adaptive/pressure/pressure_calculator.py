"""PulseFlow adaptive: Pressure Calculator.

Evaluates current system metrics and derives a deterministic, normalized
pressure score and discrete pressure state (NORMAL, HIGH, EXTREME).
"""

import time
from typing import Optional
from pydantic import BaseModel, Field

from contracts.metrics import SystemSnapshot
from adaptive.pressure.pressure_config import PressureState, PressureConfig


class PressureSnapshot(BaseModel):
    """Structured output of the adaptive pressure engine."""
    pressureState: PressureState = Field(..., description="Calculated discrete pressure state")
    pressureScore: float = Field(..., ge=0.0, le=1.0, description="Normalized pressure score (0.0 to 1.0)")
    queueDepth: int = Field(..., description="Total system queue depth")
    ingressRate: float = Field(..., description="Incoming event rate (events/sec)")
    processingRate: float = Field(..., description="Processing event rate (events/sec)")
    workerUtilization: float = Field(..., description="Overall worker pool utilization")
    latency: float = Field(..., description="Average processing latency (ms)")
    timestamp: float = Field(default_factory=time.time, description="Time of calculation")


class PressureCalculator:
    """Calculates system pressure based on pipeline metrics."""

    @classmethod
    def calculate(
        cls, 
        snapshot: SystemSnapshot, 
        ingress_rate: float = 0.0, 
        queue_capacity: Optional[int] = PressureConfig.DEFAULT_QUEUE_CAPACITY
    ) -> PressureSnapshot:
        """Evaluate a SystemSnapshot and produce a deterministic PressureSnapshot."""
        
        # 1. Queue Depth Factor
        total_depth = snapshot.queues.total_depth
        safe_capacity = queue_capacity if (queue_capacity and queue_capacity > 0) else PressureConfig.DEFAULT_QUEUE_CAPACITY
        # Assume max capacity across 3 lanes
        max_total_capacity = safe_capacity * 3
        queue_factor = min(1.0, total_depth / max_total_capacity) if max_total_capacity > 0 else 0.0
        
        # 2. Worker Utilization Factor
        util_factor = min(1.0, max(0.0, snapshot.workers.utilization))
        
        # 3. Rate Ratio Factor (Ingress vs Processing)
        if snapshot.processing_rate > 0:
            # If ingress is double processing, factor is 1.0 (max)
            rate_factor = min(1.0, ingress_rate / (snapshot.processing_rate * 2))
        elif ingress_rate > 0:
            rate_factor = 1.0
        else:
            rate_factor = 0.0
            
        # 4. Latency Factor
        latency_factor = min(1.0, snapshot.avg_latency_ms / PressureConfig.MAX_EXPECTED_LATENCY_MS)
        
        # Calculate final weighted score
        score = (
            (queue_factor * PressureConfig.WEIGHT_QUEUE_DEPTH) +
            (util_factor * PressureConfig.WEIGHT_WORKER_UTIL) +
            (rate_factor * PressureConfig.WEIGHT_RATE_RATIO) +
            (latency_factor * PressureConfig.WEIGHT_LATENCY)
        )
        score = min(1.0, max(0.0, score))  # Clamp between 0.0 and 1.0
        
        # Determine discrete state
        if score >= PressureConfig.EXTREME_THRESHOLD:
            state = PressureState.EXTREME
        elif score >= PressureConfig.HIGH_THRESHOLD:
            state = PressureState.HIGH
        else:
            state = PressureState.NORMAL
            
        return PressureSnapshot(
            pressureState=state,
            pressureScore=round(score, 4),
            queueDepth=total_depth,
            ingressRate=ingress_rate,
            processingRate=snapshot.processing_rate,
            workerUtilization=snapshot.workers.utilization,
            latency=snapshot.avg_latency_ms,
            timestamp=time.time()
        )

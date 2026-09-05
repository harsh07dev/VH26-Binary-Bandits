"""PulseFlow adaptive: Pressure Configuration.

Defines the thresholds and weights used to calculate the normalized
system pressure score and determine the discrete pressure state.
"""

from enum import Enum

class PressureState(str, Enum):
    """Discrete pressure states that drive adaptive policies."""
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    EXTREME = "EXTREME"


class PressureConfig:
    """Constants and thresholds for pressure calculations.
    
    Isolated here to prevent magic numbers scattered across the engine.
    """
    
    # State transition thresholds (for normalized score 0.0 - 1.0)
    # Calibrated so real spike bursts from TechPulse (ingress ~500/s) cross into HIGH.
    # Empirically validated: sustained 500-event batches produce scores of ~0.49,
    # so HIGH_THRESHOLD is set just below that. EXTREME is reserved for truly heavy load.
    HIGH_THRESHOLD = 0.45
    EXTREME_THRESHOLD = 0.75
    
    # Component weights for the final score (must sum to 1.0)
    WEIGHT_QUEUE_DEPTH = 0.40
    WEIGHT_WORKER_UTIL = 0.30
    WEIGHT_RATE_RATIO = 0.15
    WEIGHT_LATENCY = 0.15
    
    # Reference values for normalization
    MAX_EXPECTED_LATENCY_MS = 1000.0  # Latency at or above this maxes out the latency factor
    DEFAULT_QUEUE_CAPACITY = 1000     # Used as baseline if capacity is unbounded

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
    HIGH_THRESHOLD = 0.50
    EXTREME_THRESHOLD = 0.85
    
    # Component weights for the final score (must sum to 1.0)
    WEIGHT_QUEUE_DEPTH = 0.40
    WEIGHT_WORKER_UTIL = 0.30
    WEIGHT_RATE_RATIO = 0.15
    WEIGHT_LATENCY = 0.15
    
    # Reference values for normalization
    MAX_EXPECTED_LATENCY_MS = 1000.0  # Latency at or above this maxes out the latency factor
    DEFAULT_QUEUE_CAPACITY = 1000     # Used as baseline if capacity is unbounded

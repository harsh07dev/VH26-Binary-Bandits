"""PulseFlow adaptive: Worker Allocator.

Calculates the optimal worker distribution across priority lanes
based on the current system pressure state.
"""

from typing import Dict
from contracts.priorities import Priority
from adaptive.pressure.pressure_config import PressureState


class WorkerAllocator:
    """Calculates desired worker allocation based on pressure state."""

    @classmethod
    def calculate_desired_allocation(cls, pressure: PressureState) -> Dict[Priority, int]:
        """Determine the desired worker counts for each lane.
        
        Total capacity is strictly maintained at 8 workers to align with
        the project's configured worker pool limits, while dynamically shifting
        workers from BEST_EFFORT to CRITICAL during high load.
        """
        if pressure == PressureState.NORMAL:
            return {
                Priority.CRITICAL: 2,
                Priority.NORMAL: 4,
                Priority.BEST_EFFORT: 2,
            }
        elif pressure == PressureState.HIGH:
            return {
                Priority.CRITICAL: 3,
                Priority.NORMAL: 4,
                Priority.BEST_EFFORT: 1,
            }
        elif pressure == PressureState.EXTREME:
            return {
                Priority.CRITICAL: 4,
                Priority.NORMAL: 4,
                Priority.BEST_EFFORT: 0,
            }
            
        # Safe fallback
        return {
            Priority.CRITICAL: 2,
            Priority.NORMAL: 4,
            Priority.BEST_EFFORT: 2,
        }

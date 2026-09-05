"""PulseFlow module: traffic_profiles.

Defines workload behavior and event-rate targeting for TechPulse.
These profiles are declarative and do not perform active generation or I/O.
"""

import math
import random
import time
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, Optional


class TrafficState(str, Enum):
    """Traffic generation operational state."""
    BASELINE = "BASELINE"
    SPIKE_ACTIVE = "SPIKE_ACTIVE"


class SpikeMode(str, Enum):
    """Current spike operational mode."""
    NONE = "NONE"
    PRESET = "PRESET"
    CUSTOM_RATE = "CUSTOM_RATE"
    CUSTOM_COUNT = "CUSTOM_COUNT"


class TrafficProfile(ABC):
    """Base class for all traffic profiles.
    
    A traffic profile describes WHAT workload TechPulse should generate 
    and the TARGET EVENT RATE over time.
    """
    
    # Default standard event distribution
    DEFAULT_DISTRIBUTION = {
        "ORDER": 5.0,
        "PAYMENT": 5.0,
        "CART_ADD": 15.0,
        "INVENTORY_UPDATE": 5.0,
        "CLICK": 20.0,
        "PAGE_VIEW": 40.0,
        "LOG": 10.0
    }
    
    def __init__(self, name: str, baseline_rate: float, event_distribution: Optional[Dict[str, float]] = None):
        if baseline_rate < 0:
            raise ValueError("baseline_rate cannot be negative")
            
        self.name = name
        self.baseline_rate = float(baseline_rate)
        
        if event_distribution is None:
            self.event_distribution = self.DEFAULT_DISTRIBUTION
        else:
            self.event_distribution = event_distribution
        
        if not self.event_distribution:
            raise ValueError("Event distribution cannot be empty")
            
        for event_type, weight in self.event_distribution.items():
            if weight < 0:
                raise ValueError(f"Event probability weight cannot be negative for '{event_type}'")
                
        self._types = list(self.event_distribution.keys())
        self._weights = list(self.event_distribution.values())

    @abstractmethod
    def target_rate(self, elapsed_time: float) -> float:
        """Calculate the deterministic target event rate (events/sec) at a given elapsed time."""
        pass
        
    def get_event_type(self, rng: random.Random) -> str:
        """Pick an event type randomly based on the configured distribution."""
        return rng.choices(self._types, weights=self._weights, k=1)[0]


class SteadyProfile(TrafficProfile):
    """A constant event rate continuously."""
    
    def target_rate(self, elapsed_time: float) -> float:
        return self.baseline_rate


class RampProfile(TrafficProfile):
    """Gradually increases the event rate from baseline to target over a configured duration."""
    
    def __init__(
        self, 
        name: str, 
        baseline_rate: float, 
        target_rate: float, 
        duration: float, 
        event_distribution: Optional[Dict[str, float]] = None
    ):
        super().__init__(name, baseline_rate, event_distribution)
        if target_rate < 0:
            raise ValueError("target_rate cannot be negative")
        if duration <= 0:
            raise ValueError("duration must be positive")
            
        self.target_rate_val = float(target_rate)
        self.duration = float(duration)
        
    def target_rate(self, elapsed_time: float) -> float:
        if elapsed_time <= 0:
            return self.baseline_rate
        if elapsed_time >= self.duration:
            return self.target_rate_val
            
        # Linear interpolation
        progress = elapsed_time / self.duration
        return self.baseline_rate + (self.target_rate_val - self.baseline_rate) * progress


class SurgeProfile(TrafficProfile):
    """Increases traffic to a strict multiple (e.g., 20x) of baseline."""
    
    def __init__(
        self, 
        name: str, 
        baseline_rate: float, 
        multiplier: float = 20.0, 
        event_distribution: Optional[Dict[str, float]] = None
    ):
        super().__init__(name, baseline_rate, event_distribution)
        if multiplier <= 0:
            raise ValueError("multiplier must be positive")
        self.multiplier = float(multiplier)
        
    def target_rate(self, elapsed_time: float) -> float:
        return self.baseline_rate * self.multiplier


class HarmonicProfile(TrafficProfile):
    """A periodic workload whose rate oscillates around baseline using a sine wave."""
    
    def __init__(
        self, 
        name: str, 
        baseline_rate: float, 
        amplitude: float, 
        period: float, 
        event_distribution: Optional[Dict[str, float]] = None
    ):
        super().__init__(name, baseline_rate, event_distribution)
        if period <= 0:
            raise ValueError("period must be positive")
        if amplitude < 0.0 or amplitude > 1.0:
            raise ValueError("amplitude must be between 0.0 and 1.0 to prevent negative rates")
            
        self.amplitude = float(amplitude)
        self.period = float(period)
        
    def target_rate(self, elapsed_time: float) -> float:
        # rate(t) = baseline * (1 + amplitude * sin(2πt / period))
        return self.baseline_rate * (1.0 + self.amplitude * math.sin(2 * math.pi * elapsed_time / self.period))


class DynamicWorkloadProfile(TrafficProfile):
    """Authoritative traffic profile for TechPulse.

    Spike is a workload state, NOT a separate generator.
    The generator continuously runs at baseline rate (~100 ev/s).
    Preset and custom spike operations temporarily adjust the target rate,
    and automatically revert to baseline when duration expires or requested
    event count is completed.
    """

    def __init__(
        self,
        name: str = "dynamic_workload",
        baseline_rate: float = 100.0,
        event_distribution: Optional[Dict[str, float]] = None,
        max_custom_rate: float = 500000.0,
    ):
        super().__init__(name, baseline_rate, event_distribution)
        if max_custom_rate <= 0:
            raise ValueError("max_custom_rate must be positive")
        self.max_custom_rate = float(max_custom_rate)

        # Dynamic workload state
        self._current_target_rate: float = self.baseline_rate
        self._state: TrafficState = TrafficState.BASELINE
        self._multiplier: float = 1.0
        self._spike_mode: SpikeMode = SpikeMode.NONE
        self._spike_label: str = "Steady Baseline"
        self._spike_start_mono: Optional[float] = None
        self._spike_duration: Optional[float] = None

        # Custom event run state (applies only to the custom run)
        self._events_target: Optional[int] = None
        self._events_spiked: int = 0

        # Distribution preset metadata
        self.distribution_preset: str = "standard"
        self.distribution_label: str = "Standard Browsing"

    @property
    def state(self) -> TrafficState:
        return self._state

    @property
    def current_target_rate(self) -> float:
        return self._current_target_rate

    @property
    def multiplier(self) -> float:
        return self._multiplier

    @property
    def spike_mode(self) -> SpikeMode:
        return self._spike_mode

    @property
    def spike_label(self) -> str:
        return self._spike_label

    @property
    def spike_duration(self) -> Optional[float]:
        return self._spike_duration

    @property
    def events_target(self) -> Optional[int]:
        return self._events_target

    @property
    def events_spiked(self) -> int:
        return self._events_spiked

    @property
    def remaining_seconds(self) -> Optional[float]:
        """Remaining duration of an active time-based spike, or None."""
        if (
            self._state == TrafficState.SPIKE_ACTIVE
            and self._spike_duration is not None
            and self._spike_start_mono is not None
        ):
            elapsed = time.monotonic() - self._spike_start_mono
            return max(0.0, self._spike_duration - elapsed)
        return None

    def target_rate(self, elapsed_time: float) -> float:
        """Return the current dynamic target rate, auto-reverting if time expired."""
        if self._state == TrafficState.SPIKE_ACTIVE and self._spike_duration is not None:
            if self._spike_start_mono is not None:
                elapsed_spike = time.monotonic() - self._spike_start_mono
                if elapsed_spike >= self._spike_duration:
                    self.recover_to_baseline()

        return self._current_target_rate

    def set_preset_spike(self, multiplier: float, duration: Optional[float] = 20.0) -> float:
        """Apply a preset multiplier (e.g. 1x, 5x, 10x, 20x) to the baseline rate."""
        if multiplier <= 0:
            raise ValueError(f"multiplier must be positive, got {multiplier}")

        if duration is not None and duration <= 0:
            raise ValueError(f"duration must be positive, got {duration}")

        if multiplier == 1.0:
            self.recover_to_baseline()
            return self._current_target_rate

        new_rate = min(self.baseline_rate * multiplier, self.max_custom_rate)
        self._current_target_rate = float(new_rate)
        self._multiplier = float(multiplier)
        self._state = TrafficState.SPIKE_ACTIVE
        self._spike_mode = SpikeMode.PRESET
        self._spike_label = f"+{multiplier:g}× Preset Surge"
        self._spike_start_mono = time.monotonic()
        self._spike_duration = float(duration) if duration else None
        self._events_target = None
        self._events_spiked = 0
        return self._current_target_rate

    def set_custom_spike(self, target_rate: float, duration: float) -> float:
        """Set an arbitrary target rate and duration, within safety limits."""
        if target_rate <= 0:
            raise ValueError(f"target_rate must be > 0, got {target_rate}")
        if target_rate > self.max_custom_rate:
            raise ValueError(
                f"target_rate {target_rate} exceeds MAX_CUSTOM_RATE {self.max_custom_rate}"
            )
        if duration <= 0:
            raise ValueError(f"duration must be > 0, got {duration}")

        self._current_target_rate = float(target_rate)
        self._multiplier = (
            round(target_rate / self.baseline_rate, 2) if self.baseline_rate > 0 else 1.0
        )
        self._state = TrafficState.SPIKE_ACTIVE
        self._spike_mode = SpikeMode.CUSTOM_RATE
        self._spike_label = f"Custom Surge ({int(target_rate):,} ev/s)"
        self._spike_start_mono = time.monotonic()
        self._spike_duration = float(duration)
        self._events_target = None
        self._events_spiked = 0
        return self._current_target_rate

    def set_custom_event_run(self, total_events: int, max_rate: float) -> float:
        """Generate an exact count of events at max_rate, then automatically return to baseline."""
        if total_events <= 0:
            raise ValueError(f"total_events must be > 0, got {total_events}")
        if max_rate <= 0:
            raise ValueError(f"max_rate must be > 0, got {max_rate}")
        if max_rate > self.max_custom_rate:
            raise ValueError(
                f"max_rate {max_rate} exceeds MAX_CUSTOM_RATE {self.max_custom_rate}"
            )

        self._current_target_rate = float(max_rate)
        self._multiplier = (
            round(max_rate / self.baseline_rate, 2) if self.baseline_rate > 0 else 1.0
        )
        self._state = TrafficState.SPIKE_ACTIVE
        self._spike_mode = SpikeMode.CUSTOM_COUNT
        self._spike_label = f"Custom Run ({total_events:,} ev @ {int(max_rate):,} ev/s)"
        self._spike_start_mono = time.monotonic()
        self._spike_duration = None
        self._events_target = int(total_events)
        self._events_spiked = 0
        return self._current_target_rate

    def record_events_delivered(self, count: int) -> None:
        """Track delivered events. If a custom event run reaches its target, revert to baseline."""
        if self._state == TrafficState.SPIKE_ACTIVE and self._spike_mode == SpikeMode.CUSTOM_COUNT:
            self._events_spiked += count
            if self._events_target is not None and self._events_spiked >= self._events_target:
                self.recover_to_baseline()

    def recover_to_baseline(self) -> float:
        """Cancel active spike and immediately return to baseline rate. NEVER sets rate to 0."""
        self._state = TrafficState.BASELINE
        self._current_target_rate = self.baseline_rate
        self._multiplier = 1.0
        self._spike_mode = SpikeMode.NONE
        self._spike_label = "Steady Baseline"
        self._spike_start_mono = None
        self._spike_duration = None
        self._events_target = None
        self._events_spiked = 0
        return self._current_target_rate

    def reset(self) -> float:
        """Reset spike state and restore baseline rate."""
        return self.recover_to_baseline()

    def update_distribution(
        self,
        distribution: Dict[str, float],
        preset_id: str = "custom",
        preset_label: str = "Custom Workload Mix",
    ) -> None:
        """Update event type distribution mix with preset/custom metadata."""
        if not distribution:
            raise ValueError("Distribution cannot be empty")
        for k, v in distribution.items():
            if v < 0:
                raise ValueError(f"Weight for '{k}' cannot be negative")
        self.event_distribution = distribution
        self.distribution_preset = preset_id
        self.distribution_label = preset_label
        self._types = list(distribution.keys())
        self._weights = list(distribution.values())

    def status_dict(self) -> Dict[str, Any]:
        """Point-in-time dictionary snapshot of profile state."""
        return {
            "name": self.name,
            "state": self._state.value,
            "baseline_rate": self.baseline_rate,
            "current_target_rate": self._current_target_rate,
            "multiplier": self._multiplier,
            "spike_mode": self._spike_mode.value,
            "spike_label": self._spike_label,
            "remaining_seconds": self.remaining_seconds,
            "events_target": self._events_target,
            "events_spiked": self._events_spiked,
            "distribution": dict(self.event_distribution),
            "distribution_preset": self.distribution_preset,
            "distribution_label": self.distribution_label,
        }


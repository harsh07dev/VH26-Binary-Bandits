"""PulseFlow module: traffic_profiles.

Defines workload behavior and event-rate targeting for TechPulse.
These profiles are declarative and do not perform active generation or I/O.
"""

import math
import random
from abc import ABC, abstractmethod
from typing import Dict, Optional


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

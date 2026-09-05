"""PulseFlow adaptive: Probabilistic Sampler.

Provides a configurable probabilistic sampler for down-sampling low-priority
(BEST_EFFORT) events during elevated system pressure states (e.g. HIGH pressure).
"""

import os
import random
from typing import Optional
from contracts.events import Event


class ProbabilisticSampler:
    """Configurable probabilistic sampler for event stream down-sampling."""

    def __init__(self, sample_rate: float = 0.5, seed: Optional[int] = None) -> None:
        """Initialize the sampler.

        Args:
            sample_rate: Probability (0.0 to 1.0) of keeping an event.
                         0.0 means drop all events; 1.0 means keep all events.
            seed: Optional random seed for deterministic sampling in tests.
        """
        self.set_sample_rate(sample_rate)
        self._rng = random.Random(seed)
        self.total_evaluated: int = 0
        self.kept_count: int = 0
        self.dropped_count: int = 0

    def set_sample_rate(self, rate: float) -> None:
        """Update the sample rate."""
        if not (0.0 <= rate <= 1.0):
            raise ValueError(f"Sample rate must be between 0.0 and 1.0, got {rate}")
        self.sample_rate = float(rate)

    def get_sample_rate(self) -> float:
        """Return current sample rate."""
        return self.sample_rate

    def set_seed(self, seed: Optional[int]) -> None:
        """Reset internal RNG with a seed for deterministic behavior."""
        self._rng = random.Random(seed)

    def should_keep(self, event: Optional[Event] = None) -> bool:
        """Evaluate whether an incoming event should be kept or dropped.

        Args:
            event: Optional Event object for inspection.

        Returns:
            True if event should be kept (routed to queue),
            False if event should be dropped (sampled out).
        """
        self.total_evaluated += 1

        if self.sample_rate <= 0.0:
            keep = False
        elif self.sample_rate >= 1.0:
            keep = True
        else:
            keep = self._rng.random() < self.sample_rate

        if keep:
            self.kept_count += 1
        else:
            self.dropped_count += 1

        return keep

    def reset_metrics(self) -> None:
        """Reset internal metrics counters."""
        self.total_evaluated = 0
        self.kept_count = 0
        self.dropped_count = 0


# Default shared instance with configurable environment override
_default_rate = float(os.getenv("PULSEFLOW_SAMPLE_RATE", "0.5"))
adaptive_sampler = ProbabilisticSampler(sample_rate=_default_rate)

__all__ = ["ProbabilisticSampler", "adaptive_sampler"]

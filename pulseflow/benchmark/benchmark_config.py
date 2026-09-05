"""PulseFlow Benchmark: Configuration and Scenario Presets.

Defines standardized presets and workload parameters for objective, reproducible
comparative benchmarking between the Naive FIFO Pipeline and the PulseFlow Pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class BenchmarkScenario(str, Enum):
    """Standardized benchmark scenarios conforming to specification."""
    NORMAL = "NORMAL"
    HIGH_LOAD = "HIGH_LOAD"
    FLASH_SALE = "FLASH_SALE"
    TELEMETRY_FLOOD = "TELEMETRY_FLOOD"
    CRITICAL_HEAVY = "CRITICAL_HEAVY"
    CUSTOM = "CUSTOM"


# Standard e-commerce distribution:
# Critical (Orders, Payments): 10%
# Normal (Cart adds, Inventory updates): 30%
# Best-effort (Clicks, Page views, Logs): 60%
STANDARD_DISTRIBUTION: Dict[str, float] = {
    "ORDER": 0.05,
    "PAYMENT": 0.05,
    "CART_ADD": 0.20,
    "INVENTORY_UPDATE": 0.10,
    "CLICK": 0.30,
    "PAGE_VIEW": 0.25,
    "LOG": 0.05,
}

TELEMETRY_FLOOD_DISTRIBUTION: Dict[str, float] = {
    "ORDER": 0.04,
    "PAYMENT": 0.04,
    "CART_ADD": 0.10,
    "INVENTORY_UPDATE": 0.05,
    "CLICK": 0.40,
    "PAGE_VIEW": 0.30,
    "LOG": 0.07,
}

CRITICAL_HEAVY_DISTRIBUTION: Dict[str, float] = {
    "ORDER": 0.25,
    "PAYMENT": 0.25,
    "CART_ADD": 0.20,
    "INVENTORY_UPDATE": 0.10,
    "CLICK": 0.10,
    "PAGE_VIEW": 0.08,
    "LOG": 0.02,
}


@dataclass
class BenchmarkConfig:
    """Benchmark workload configuration definition."""
    scenario: BenchmarkScenario = BenchmarkScenario.FLASH_SALE
    total_events: int = 100_000
    target_rate: float = 2_000.0  # events per second
    seed: int = 42
    distribution: Dict[str, float] = field(default_factory=lambda: dict(STANDARD_DISTRIBUTION))
    description: str = ""
    # Simulation acceleration parameter (e.g. 1.0 = real-time, 10.0 = 10x faster execution for testing)
    time_dilation: float = 1.0

    @property
    def duration_seconds(self) -> float:
        if self.target_rate <= 0:
            return 0.0
        return round(self.total_events / self.target_rate, 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario": self.scenario.value,
            "total_events": self.total_events,
            "target_rate": self.target_rate,
            "seed": self.seed,
            "duration_sec": self.duration_seconds,
            "distribution": dict(self.distribution),
            "description": self.description,
        }

    @classmethod
    def from_scenario(
        cls,
        scenario: BenchmarkScenario | str,
        total_events: Optional[int] = None,
        target_rate: Optional[float] = None,
        seed: Optional[int] = None,
        distribution: Optional[Dict[str, float]] = None,
    ) -> "BenchmarkConfig":
        """Factory creating benchmark configs from presets or custom parameters."""
        if isinstance(scenario, str):
            scenario = BenchmarkScenario(scenario)

        actual_seed = seed if seed is not None else 42

        if scenario == BenchmarkScenario.NORMAL:
            return cls(
                scenario=scenario,
                total_events=total_events or 10_000,
                target_rate=target_rate or 100.0,
                seed=actual_seed,
                distribution=distribution or dict(STANDARD_DISTRIBUTION),
                description="Scenario 1: Normal steady-state traffic (100 ev/s, 10,000 events)",
            )
        elif scenario == BenchmarkScenario.HIGH_LOAD:
            return cls(
                scenario=scenario,
                total_events=total_events or 25_000,
                target_rate=target_rate or 500.0,
                seed=actual_seed,
                distribution=distribution or dict(STANDARD_DISTRIBUTION),
                description="Scenario 2: High sustained load (500 ev/s, 25,000 events)",
            )
        elif scenario == BenchmarkScenario.FLASH_SALE:
            return cls(
                scenario=scenario,
                total_events=total_events or 100_000,
                target_rate=target_rate or 2_000.0,
                seed=actual_seed,
                distribution=distribution or dict(STANDARD_DISTRIBUTION),
                description="Scenario 3: 20x Flash Sale surge (2,000 ev/s, 100,000 events)",
            )
        elif scenario == BenchmarkScenario.TELEMETRY_FLOOD:
            return cls(
                scenario=scenario,
                total_events=total_events or 100_000,
                target_rate=target_rate or 2_000.0,
                seed=actual_seed,
                distribution=distribution or dict(TELEMETRY_FLOOD_DISTRIBUTION),
                description="Scenario 4: Massive telemetry flood (Clicks/Views/Logs dominant)",
            )
        elif scenario == BenchmarkScenario.CRITICAL_HEAVY:
            return cls(
                scenario=scenario,
                total_events=total_events or 100_000,
                target_rate=target_rate or 2_000.0,
                seed=actual_seed,
                distribution=distribution or dict(CRITICAL_HEAVY_DISTRIBUTION),
                description="Scenario 5: Critical heavy load (50% Orders & Payments)",
            )
        else:  # CUSTOM
            return cls(
                scenario=BenchmarkScenario.CUSTOM,
                total_events=total_events or 50_000,
                target_rate=target_rate or 1_000.0,
                seed=actual_seed,
                distribution=distribution or dict(STANDARD_DISTRIBUTION),
                description="Custom user-configured benchmark workload",
            )

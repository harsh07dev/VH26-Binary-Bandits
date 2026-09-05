"""PulseFlow module: models.

Request and response schemas for TechPulse Workload Generator Control API.
"""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class PresetSpikeRequest(BaseModel):
    """Request to activate a preset multiplier spike."""
    multiplier: float = Field(..., gt=0, description="Multiplier factor against baseline rate (e.g. 1.0, 5.0, 10.0, 20.0)")
    duration: Optional[float] = Field(default=20.0, gt=0, description="Duration in seconds before returning to baseline")


class CustomSpikeRequest(BaseModel):
    """Request to activate an arbitrary rate spike."""
    target_rate: float = Field(..., gt=0, description="Arbitrary target event rate in events/sec")
    duration: float = Field(..., gt=0, description="Duration in seconds before returning to baseline")


class CustomRunRequest(BaseModel):
    """Request to generate an exact count of events at max rate, then return to baseline."""
    total_events: int = Field(..., gt=0, description="Exact number of events to generate")
    max_rate: float = Field(..., gt=0, description="Maximum throughput cap in events/sec")


class DistributionUpdateRequest(BaseModel):
    """Request to update event type distribution mix."""
    distribution: Dict[str, float] = Field(..., description="Map of event_type to probability weight")
    preset_id: Optional[str] = Field(default="custom", description="Preset archetype identifier or 'custom'")
    preset_label: Optional[str] = Field(default="Custom Workload Mix", description="Human-readable label for distribution")


class CustomMixSpikeRequest(BaseModel):
    """Request to update distribution mix and trigger rate spike simultaneously."""
    target_rate: float = Field(..., gt=0, description="Arbitrary target event rate in events/sec")
    duration: float = Field(..., gt=0, description="Duration in seconds before returning to baseline")
    distribution: Optional[Dict[str, float]] = Field(default=None, description="Optional map of event_type to probability weight")
    preset_id: Optional[str] = Field(default="custom", description="Preset archetype identifier or 'custom'")
    preset_label: Optional[str] = Field(default="Custom Workload Mix", description="Human-readable label for distribution")


class TechPulseStatusResponse(BaseModel):
    """Authoritative point-in-time telemetry and state snapshot."""
    running: bool
    state: str
    baseline_rate: float
    current_target_rate: float
    measured_rate: float
    multiplier: float
    spike_mode: str
    spike_label: str
    remaining_seconds: Optional[float] = None
    events_target: Optional[int] = None
    events_spiked: int = 0
    events_generated: int
    events_attempted: int
    events_delivered: int
    events_failed: int
    batches_generated: int
    batches_delivered: int
    errors: int
    elapsed_time: float
    pulseflow_url: str
    pulseflow_connected: bool
    pulseflow_latency_ms: float
    distribution: Dict[str, float]
    distribution_preset: str = "standard"
    distribution_label: str = "Standard Browsing"

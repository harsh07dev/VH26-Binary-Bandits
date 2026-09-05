"""PulseFlow module: routes.

FastAPI router and endpoints for the TechPulse Workload Generator Control API.
"""

import logging
import time
from typing import Optional

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from techpulse import config
from techpulse.app.models import (
    CustomMixSpikeRequest,
    CustomRunRequest,
    CustomSpikeRequest,
    DistributionUpdateRequest,
    PresetSpikeRequest,
    TechPulseStatusResponse,
)
from techpulse.client.pulseflow_client import PulseFlowClient
from techpulse.generator.traffic_generator import TrafficGenerator
from techpulse.generator.traffic_profiles import DynamicWorkloadProfile

logger = logging.getLogger(__name__)


class TechPulseContext:
    """Shared state container connecting the running TrafficGenerator to HTTP endpoints."""

    def __init__(self) -> None:
        self.generator: Optional[TrafficGenerator] = None
        self.profile: Optional[DynamicWorkloadProfile] = None
        self.client: Optional[PulseFlowClient] = None
        self.pulseflow_connected: bool = False
        self.pulseflow_latency_ms: float = 0.0

    def set_instance(
        self,
        generator: TrafficGenerator,
        profile: DynamicWorkloadProfile,
        client: PulseFlowClient,
    ) -> None:
        self.generator = generator
        self.profile = profile
        self.client = client


# Singleton instance shared by the FastAPI app
context = TechPulseContext()

router = APIRouter()


@router.get("/health")
async def health_check() -> dict:
    """Liveness probe for TechPulse Control API."""
    return {
        "status": "ok",
        "service": "techpulse-generator",
        "running": context.generator.is_running if context.generator else False,
    }


@router.get("/metrics", response_model=TechPulseStatusResponse)
async def get_metrics() -> TechPulseStatusResponse:
    """Return point-in-time authoritative metrics from the Python TrafficGenerator."""
    if not context.generator or not context.profile:
        raise HTTPException(status_code=503, detail="TechPulse generator not initialized")

    stats = context.generator.stats()
    profile = context.profile

    return TechPulseStatusResponse(
        running=stats.running,
        state=stats.state,
        baseline_rate=profile.baseline_rate,
        current_target_rate=profile.current_target_rate,
        measured_rate=stats.measured_rate,
        multiplier=stats.multiplier,
        spike_mode=stats.spike_mode,
        spike_label=stats.spike_label,
        remaining_seconds=stats.remaining_seconds,
        events_target=profile.events_target,
        events_spiked=profile.events_spiked,
        events_generated=stats.events_generated,
        events_attempted=stats.events_attempted,
        events_delivered=stats.events_delivered,
        events_failed=stats.events_failed,
        batches_generated=stats.batches_generated,
        batches_delivered=stats.batches_delivered,
        errors=stats.errors,
        elapsed_time=stats.elapsed_time,
        pulseflow_url=config.PIPELINE_BASE_URL,
        pulseflow_connected=context.pulseflow_connected,
        pulseflow_latency_ms=context.pulseflow_latency_ms,
        distribution=dict(profile.event_distribution),
        distribution_preset=getattr(profile, "distribution_preset", "custom"),
        distribution_label=getattr(profile, "distribution_label", "Custom Workload Mix"),
    )


@router.post("/control/preset")
async def apply_preset_spike(req: PresetSpikeRequest) -> dict:
    """Set a preset multiplier spike (e.g. 1x, 5x, 10x, 20x)."""
    if not context.profile:
        raise HTTPException(status_code=503, detail="Generator profile not initialized")
    try:
        new_rate = context.profile.set_preset_spike(req.multiplier, req.duration)
        return {
            "status": "ok",
            "message": f"Applied {req.multiplier:g}x preset",
            "multiplier": req.multiplier,
            "target_rate": new_rate,
            "duration": req.duration,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/control/custom-spike")
async def apply_custom_spike(req: CustomSpikeRequest) -> dict:
    """Set an arbitrary target rate and duration."""
    if not context.profile:
        raise HTTPException(status_code=503, detail="Generator profile not initialized")
    try:
        new_rate = context.profile.set_custom_spike(req.target_rate, req.duration)
        return {
            "status": "ok",
            "message": f"Custom spike active: {req.target_rate:g} ev/s for {req.duration:g}s",
            "target_rate": new_rate,
            "duration": req.duration,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/control/custom-mix-spike")
async def apply_custom_mix_spike(req: CustomMixSpikeRequest) -> dict:
    """Update event mix weights and trigger a custom rate spike simultaneously."""
    if not context.profile:
        raise HTTPException(status_code=503, detail="Generator profile not initialized")
    try:
        if req.distribution:
            preset_id = req.preset_id or "custom"
            preset_label = req.preset_label or ("Standard Browsing" if preset_id == "standard" else "Custom Workload Mix")
            context.profile.update_distribution(req.distribution, preset_id=preset_id, preset_label=preset_label)
        new_rate = context.profile.set_custom_spike(req.target_rate, req.duration)
        return {
            "status": "ok",
            "message": f"Custom mix spike active: {req.target_rate:g} ev/s for {req.duration:g}s",
            "target_rate": new_rate,
            "duration": req.duration,
            "distribution": context.profile.event_distribution,
            "distribution_preset": context.profile.distribution_preset,
            "distribution_label": context.profile.distribution_label,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/control/custom-run")
async def apply_custom_run(req: CustomRunRequest) -> dict:
    """Set an exact event-count benchmark run."""
    if not context.profile:
        raise HTTPException(status_code=503, detail="Generator profile not initialized")
    try:
        new_rate = context.profile.set_custom_event_run(req.total_events, req.max_rate)
        return {
            "status": "ok",
            "message": f"Custom run started: {req.total_events:,} events at max {req.max_rate:g} ev/s",
            "total_events": req.total_events,
            "max_rate": new_rate,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/control/recover")
async def recover_to_baseline() -> dict:
    """Cancel active spike and immediately return to baseline rate. Never sets rate to 0."""
    if not context.profile:
        raise HTTPException(status_code=503, detail="Generator profile not initialized")
    baseline_rate = context.profile.recover_to_baseline()
    return {
        "status": "ok",
        "message": "Recovered to steady baseline",
        "target_rate": baseline_rate,
    }


@router.post("/control/reset")
async def reset_session() -> dict:
    """Reset multiplier to 1x, restore baseline rate, and reset session counters."""
    if not context.profile:
        raise HTTPException(status_code=503, detail="Generator profile not initialized")
    baseline_rate = context.profile.reset()
    if context.generator and hasattr(context.generator, "reset_stats"):
        context.generator.reset_stats()
    return {
        "status": "ok",
        "message": "Reset to baseline rate and cleared session stats",
        "target_rate": baseline_rate,
    }


@router.post("/control/pause")
async def pause_generator() -> dict:
    """Gracefully pause the generation loop."""
    if not context.generator:
        raise HTTPException(status_code=503, detail="Generator not initialized")
    if context.generator.is_running:
        await context.generator.stop()
    return {"status": "ok", "running": context.generator.is_running}


@router.post("/control/resume")
async def resume_generator() -> dict:
    """Resume the generation loop."""
    if not context.generator:
        raise HTTPException(status_code=503, detail="Generator not initialized")
    if not context.generator.is_running:
        await context.generator.start()
    return {"status": "ok", "running": context.generator.is_running}


@router.post("/control/distribution")
async def update_distribution(req: DistributionUpdateRequest) -> dict:
    """Update event mix weights with preset/custom metadata."""
    if not context.profile:
        raise HTTPException(status_code=503, detail="Generator profile not initialized")
    try:
        preset_id = req.preset_id or "custom"
        preset_label = req.preset_label or ("Standard Browsing" if preset_id == "standard" else "Custom Workload Mix")
        context.profile.update_distribution(req.distribution, preset_id=preset_id, preset_label=preset_label)
        return {
            "status": "ok",
            "distribution": context.profile.event_distribution,
            "distribution_preset": context.profile.distribution_preset,
            "distribution_label": context.profile.distribution_label,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def create_app() -> FastAPI:
    """Create and configure the TechPulse Control API FastAPI application."""
    app = FastAPI(
        title="TechPulse Control & Telemetry API",
        description="Authoritative control plane for TechPulse workload generator (Machine 1)",
        version="1.0.0",
    )

    # Enable CORS for local and network frontends
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    return app

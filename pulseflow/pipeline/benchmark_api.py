"""PulseFlow Pipeline: Benchmark REST API Endpoints.

Provides endpoints for running head-to-head benchmarks between Naive FIFO and PulseFlow,
querying scenario presets, and fetching historical benchmark records.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from benchmark.benchmark_config import (
    BenchmarkConfig,
    BenchmarkScenario,
    STANDARD_DISTRIBUTION,
    TELEMETRY_FLOOD_DISTRIBUTION,
    CRITICAL_HEAVY_DISTRIBUTION,
)
from benchmark.benchmark_storage import (
    get_benchmark_result,
    list_benchmark_results,
)
from benchmark.runner import execute_head_to_head_benchmark


router = APIRouter(prefix="/benchmark", tags=["Benchmark & Comparison"])


class BenchmarkRunRequest(BaseModel):
    scenario: str = Field(default="FLASH_SALE", description="Scenario preset name or CUSTOM")
    mode: str = Field(default="both", description="Execution mode: 'both', 'naive', or 'pulseflow'")
    total_events: Optional[int] = Field(default=None, description="Override total event count")
    target_rate: Optional[float] = Field(default=None, description="Override target rate (ev/s)")
    seed: Optional[int] = Field(default=42, description="Random seed for reproducible workload")
    distribution: Optional[Dict[str, float]] = Field(default=None, description="Custom event type weights")
    fast_simulation: bool = Field(default=True, description="Accelerated execution mode for interactive benchmarking")


@router.get("/scenarios")
async def get_benchmark_scenarios() -> Dict[str, Any]:
    """List available benchmark scenarios and their default workload profiles."""
    scenarios = [
        {
            "id": BenchmarkScenario.NORMAL.value,
            "name": "Normal Steady-State",
            "description": "Baseline nominal load without resource pressure",
            "target_rate": 100.0,
            "total_events": 10_000,
            "duration_sec": 100.0,
            "distribution": STANDARD_DISTRIBUTION,
        },
        {
            "id": BenchmarkScenario.HIGH_LOAD.value,
            "name": "High Sustained Load",
            "description": "5x elevated throughput with approaching buffer limits",
            "target_rate": 500.0,
            "total_events": 25_000,
            "duration_sec": 50.0,
            "distribution": STANDARD_DISTRIBUTION,
        },
        {
            "id": BenchmarkScenario.FLASH_SALE.value,
            "name": "Flash Sale Surge (20x)",
            "description": "2,000 ev/s sudden extreme spike causing naive buffer overflow",
            "target_rate": 2000.0,
            "total_events": 100_000,
            "duration_sec": 50.0,
            "distribution": STANDARD_DISTRIBUTION,
        },
        {
            "id": BenchmarkScenario.TELEMETRY_FLOOD.value,
            "name": "Telemetry Flood",
            "description": "Extreme flood of Clicks/Views/Logs with small percentage of orders",
            "target_rate": 2000.0,
            "total_events": 100_000,
            "duration_sec": 50.0,
            "distribution": TELEMETRY_FLOOD_DISTRIBUTION,
        },
        {
            "id": BenchmarkScenario.CRITICAL_HEAVY.value,
            "name": "Critical Heavy Load",
            "description": "50% revenue transactions (Orders & Payments) under heavy pressure",
            "target_rate": 2000.0,
            "total_events": 100_000,
            "duration_sec": 50.0,
            "distribution": CRITICAL_HEAVY_DISTRIBUTION,
        },
        {
            "id": BenchmarkScenario.CUSTOM.value,
            "name": "Custom Workload",
            "description": "Fully user-configured event volume, rate, and distribution",
            "target_rate": 1000.0,
            "total_events": 50_000,
            "duration_sec": 50.0,
            "distribution": STANDARD_DISTRIBUTION,
        },
    ]
    return {"scenarios": scenarios}


@router.post("/run")
async def run_benchmark(req: BenchmarkRunRequest) -> Dict[str, Any]:
    """Execute a head-to-head benchmark run and return normalized comparison results."""
    try:
        scenario_enum = BenchmarkScenario(req.scenario.upper())
    except ValueError:
        scenario_enum = BenchmarkScenario.CUSTOM

    cfg = BenchmarkConfig.from_scenario(
        scenario=scenario_enum,
        total_events=req.total_events,
        target_rate=req.target_rate,
        seed=req.seed,
        distribution=req.distribution,
    )

    result = await execute_head_to_head_benchmark(
        config=cfg,
        mode=req.mode.lower(),
        fast_simulation=req.fast_simulation,
    )

    return result


@router.get("/history")
async def get_benchmark_history(limit: int = Query(default=50, ge=1, le=200)) -> Dict[str, Any]:
    """List historical benchmark run summaries."""
    history = list_benchmark_results(limit=limit)
    return {"count": len(history), "benchmarks": history}


@router.get("/results/{benchmark_id}")
async def get_benchmark_by_id(benchmark_id: str) -> Dict[str, Any]:
    """Retrieve full normalized benchmark result object by benchmark_id."""
    res = get_benchmark_result(benchmark_id)
    if not res:
        raise HTTPException(status_code=404, detail=f"Benchmark '{benchmark_id}' not found.")
    return res

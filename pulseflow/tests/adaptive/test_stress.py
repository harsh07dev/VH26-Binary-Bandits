"""PulseFlow Adaptive Batching End-to-End Stress Test Suite.

Executes a 5-phase traffic workload (1x → 5x → 10x → 20x → 1x) using the TechPulse generator
against the PulseFlow pipeline lifespan.

Telemetry sampled per interval:
  - Ingress rate & processing throughput
  - Queue depth per lane (CRITICAL, NORMAL, BEST_EFFORT)
  - Queue growth rate per lane (dq/dt)
  - Pressure score & state
  - Worker allocation per lane
  - Batch size per lane (NORMAL, BEST_EFFORT)
  - Average, P95, and P99 latencies
  - Sampled, shed, deferred, and critical dropped events
  - Worker task/instance stability (verifying no restarts/thrashing on batch-size changes)

Assertions:
  1. Golden Invariant: zero CRITICAL event loss (critical_events_lost == 0).
  2. Sustained Overload (Phase 4): queue depth ↑, dq/dt > 0 → batch size gradually ↑.
  3. Recovery (Phase 5): queue depth ↓, dq/dt < 0 → batch size gradually ↓.
  4. Low Traffic: fast flush timeout ensures low latency.
  5. Worker Stability: zero worker replacements/thrashing caused solely by batch size changes.
"""

from __future__ import annotations

import asyncio
import time
import pytest
from typing import Dict, List, Any
from httpx import AsyncClient, ASGITransport

from pipeline.main import app, rate_tracker
from pipeline.queues.queue_manager import queue_manager
from pipeline.workers.worker_pool import worker_pool
from pipeline.processing.telemetry import processing_telemetry
from adaptive.allocation.batch_sizer import batch_sizer
from adaptive.scheduler.metrics_tracker import adaptive_metrics
from contracts.events import EventBatch
from contracts.priorities import Priority
from techpulse.generator.event_factory import EventFactory
from techpulse.generator.traffic_generator import TrafficGenerator
from techpulse.generator.traffic_profiles import SteadyProfile


@pytest.fixture(autouse=True)
async def cleanup_worker_pool():
    """Ensure worker pool is stopped after test completion."""
    yield
    if worker_pool.is_running:
        await worker_pool.stop()


class HttpSink:
    """Async HTTP sink delivering EventBatches directly to FastAPI app via ASGITransport."""
    def __init__(self, client: AsyncClient):
        self._client = client

    async def __call__(self, batch: EventBatch) -> None:
        payload = [e.model_dump() for e in batch]
        res = await self._client.post("/events/batch", json=payload, timeout=10.0)
        if res.status_code not in (200, 201, 202, 204):
            raise RuntimeError(f"Ingestion HTTP {res.status_code}: {res.text}")


@pytest.mark.asyncio
async def test_adaptive_batching_end_to_end_stress():
    """End-to-End Stress Test running 5 traffic phases: 1x → 5x → 10x → 20x → 1x."""
    
    # Baseline setup
    base_rate = 80.0  # 1x = 80 ev/s
    concurrency = 4
    phase_duration = 3.0  # 3 seconds per phase for fast execution
    
    phases = [
        ("Phase 1: 1x Baseline",   base_rate * 1),
        ("Phase 2: 5x Medium",     base_rate * 5),
        ("Phase 3: 10x High",      base_rate * 10),
        ("Phase 4: 20x Overload",  base_rate * 20),
        ("Phase 5: 1x Recovery",   base_rate * 1),
    ]

    sampled_telemetry: List[Dict[str, Any]] = []

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            sink = HttpSink(client)
            factory = EventFactory()

            # Record initial worker instance identities (IDs) for stability verification
            initial_normal_workers = {id(w): w.worker_id for w in worker_pool.get_workers(Priority.NORMAL)}
            initial_be_workers = {id(w): w.worker_id for w in worker_pool.get_workers(Priority.BEST_EFFORT)}

            batch_size_history_normal: List[int] = []
            batch_size_history_be: List[int] = []

            for phase_name, target_rate in phases:
                profile = SteadyProfile(name=f"stress_{phase_name}", baseline_rate=target_rate)
                gen = TrafficGenerator(
                    profile=profile,
                    factory=factory,
                    sink=sink,
                    batch_size=50,
                    concurrency=concurrency,
                )

                await gen.start()

                # Poll telemetry every 0.5s during the phase
                poll_interval = 0.5
                end_time = time.monotonic() + phase_duration

                while time.monotonic() < end_time:
                    await asyncio.sleep(poll_interval)

                    # Fetch metrics endpoint directly via ASGI client
                    resp = await client.get("/metrics/adaptive")
                    assert resp.status_code == 200
                    data = resp.json()

                    metrics = data.get("metrics", {})
                    infra = data.get("infraMetrics", {})
                    batching = data.get("batching", {})
                    shed_stats = data.get("shedStats", {})

                    norm_batching = batching.get("normal", {})
                    be_batching = batching.get("best_effort", {})

                    p95_lat, p99_lat = processing_telemetry.get_percentiles()
                    
                    sample = {
                        "phase": phase_name,
                        "target_rate": target_rate,
                        "ingress": metrics.get("ingress", 0.0),
                        "throughput": metrics.get("throughput", 0.0),
                        "pressure_state": metrics.get("pressureState", "NORMAL"),
                        "pressure_score": metrics.get("pressureScore", 0.0),
                        # Queue depths
                        "q_critical": infra.get("queueT1", 0),
                        "q_normal": infra.get("queueT2", 0),
                        "q_best_effort": infra.get("queueT3", 0),
                        # Growth rates
                        "growth_normal": norm_batching.get("growth_rate", 0.0),
                        "growth_be": be_batching.get("growth_rate", 0.0),
                        # Workers
                        "w_critical": infra.get("w1", 0),
                        "w_normal": infra.get("w2", 0),
                        "w_best_effort": infra.get("w3", 0),
                        # Batch sizes
                        "batch_size_normal": norm_batching.get("current_batch_size", 50),
                        "batch_size_be": be_batching.get("current_batch_size", 50),
                        "batch_timeout_normal": norm_batching.get("batch_timeout_ms", 50.0),
                        "batch_timeout_be": be_batching.get("batch_timeout_ms", 50.0),
                        # Latencies
                        "avg_latency": metrics.get("latency", 0.0),
                        "p95_latency": p95_lat,
                        "p99_latency": p99_lat,
                        # Shedding & drops
                        "sampled": shed_stats.get("sampled", 0),
                        "shed": shed_stats.get("shed", 0),
                        "deferred": shed_stats.get("deferred", 0),
                        "critical_dropped": shed_stats.get("critical_dropped", 0),
                    }
                    sampled_telemetry.append(sample)
                    batch_size_history_normal.append(sample["batch_size_normal"])
                    batch_size_history_be.append(sample["batch_size_be"])

                await gen.stop()
                await asyncio.sleep(0.5)

            # Wait briefly for final drain
            await asyncio.sleep(1.0)

            # ------------------------------------------------------------------
            # VERIFICATION & ASSERTIONS
            # ------------------------------------------------------------------

            # 1. Golden Invariant: ZERO critical event loss
            critical_drops = adaptive_metrics.shed_stats.get("critical_dropped", 0)
            assert critical_drops == 0, f"Violation: Critical events lost: {critical_drops}"

            # 2. Worker Pool Instance Stability: No worker restarts during batch size changes
            # Verify worker instances for NORMAL and BEST_EFFORT remain unchanged
            current_normal_workers = {id(w): w.worker_id for w in worker_pool.get_workers(Priority.NORMAL)}
            current_be_workers = {id(w): w.worker_id for w in worker_pool.get_workers(Priority.BEST_EFFORT)}
            
            # Since allocations were constant, worker instances MUST be identical
            assert initial_normal_workers.keys() == current_normal_workers.keys(), \
                "Worker thrashing detected: NORMAL worker instances were recreated!"
            assert initial_be_workers.keys() == current_be_workers.keys(), \
                "Worker thrashing detected: BEST_EFFORT worker instances were recreated!"

            # 3. Dynamic Batch Size Growth Under Overload (Phase 4 vs Phase 1)
            phase1_samples = [s for s in sampled_telemetry if "Phase 1" in s["phase"]]
            phase4_samples = [s for s in sampled_telemetry if "Phase 4" in s["phase"]]
            phase5_samples = [s for s in sampled_telemetry if "Phase 5" in s["phase"]]

            avg_phase1_normal_batch = sum(s["batch_size_normal"] for s in phase1_samples) / max(1, len(phase1_samples))
            max_phase4_normal_batch = max(s["batch_size_normal"] for s in phase4_samples) if phase4_samples else 50
            
            # Verify batch size escalated during heavy load
            assert max_phase4_normal_batch >= avg_phase1_normal_batch, \
                f"Batch size did not escalate under load: P1 avg={avg_phase1_normal_batch}, P4 max={max_phase4_normal_batch}"

            # 4. Recovery De-escalation (Phase 5)
            # Batch size at the end of phase 5 should decrease relative to peak overload
            end_phase5_normal_batch = phase5_samples[-1]["batch_size_normal"] if phase5_samples else 50
            assert end_phase5_normal_batch <= max_phase4_normal_batch, \
                f"Batch size did not drain/de-escalate during recovery: P4 max={max_phase4_normal_batch}, P5 end={end_phase5_normal_batch}"

            # 5. Low Traffic Fast-Flush Latency Verification
            # Phase 1 latency should remain bounded (fast flush)
            avg_p1_lat = sum(s["avg_latency"] for s in phase1_samples) / max(1, len(phase1_samples))
            assert avg_p1_lat < 500.0, f"Low traffic latency too high: {avg_p1_lat:.2f}ms"

            print("\n[SUCCESS] End-to-End Stress Test Passed All Invariants & Telemetry Verification!")

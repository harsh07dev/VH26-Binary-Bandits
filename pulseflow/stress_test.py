"""PulseFlow Adaptive Stress Test.

Drives TechPulse traffic at escalating rates and records adaptive telemetry at each phase.
Traffic phases: 1x → 5x → 10x → 20x → 1x (recovery)
Baseline: 100 ev/s  concurrency=4

Usage:
    python stress_test.py [--base-rate N] [--duration N] [--host URL]

Outputs a phase-by-phase table of all adaptive metrics.
"""

import argparse
import asyncio
import httpx
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

# ── Runtime imports from the PulseFlow source tree ─────────────────────────────
sys.path.insert(0, ".")   # run from pulseflow/ directory

from contracts.events import EventBatch
from techpulse.generator.event_factory import EventFactory
from techpulse.generator.traffic_generator import TrafficGenerator
from techpulse.generator.traffic_profiles import SteadyProfile


# ── Config ──────────────────────────────────────────────────────────────────────
PIPELINE_BASE = "http://127.0.0.1:8000"
BATCH_ENDPOINT = f"{PIPELINE_BASE}/events/batch"
METRICS_ADAPTIVE = f"{PIPELINE_BASE}/metrics/adaptive"
METRICS_QUEUES   = f"{PIPELINE_BASE}/metrics/queues"
METRICS_WORKERS  = f"{PIPELINE_BASE}/metrics/workers"

DEFAULT_BASE_RATE   = 100.0    # ev/s  → "1x"
DEFAULT_PHASE_SEC   = 20       # seconds per phase
DEFAULT_CONCURRENCY = 4        # concurrent async producers


# ── Async HTTP sink wrapping httpx ──────────────────────────────────────────────
class AsyncSink:
    """Thread-safe async HTTP sink using a shared httpx.AsyncClient."""
    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def __call__(self, batch: EventBatch) -> None:
        payload = {"events": [e.model_dump() for e in batch]}
        r = await self._client.post(BATCH_ENDPOINT, json=payload, timeout=15.0)
        if r.status_code not in (200, 201, 202, 204):
            raise RuntimeError(f"HTTP {r.status_code}")


# ── Metrics snapshot ────────────────────────────────────────────────────────────
@dataclass
class PhaseSnapshot:
    phase_name: str
    target_rate: float
    duration_s: float
    # Observed
    pressure_score_min: float = 0.0
    pressure_score_max: float = 0.0
    pressure_score_end: float = 0.0
    pressure_state: str = "NORMAL"
    # Queue depths
    q_critical: int = 0
    q_normal: int = 0
    q_best_effort: int = 0
    # Workers
    w_critical: int = 0
    w_normal: int = 0
    w_best_effort: int = 0
    # Latency & rate
    avg_latency_ms: float = 0.0
    processing_rate: float = 0.0
    # Actions
    normal_action: str = "STREAM"
    be_action: str = "STREAM"
    # Counts
    sampled: int = 0
    sampled_kept: int = 0
    sampled_dropped: int = 0
    shed: int = 0
    deferred: int = 0
    critical_dropped: int = 0
    # Generator
    events_sent: int = 0
    generator_errors: int = 0


async def poll_metrics(client: httpx.AsyncClient) -> Dict[str, Any]:
    """Fetch and merge all metric endpoints."""
    results = {}
    try:
        r = await client.get(METRICS_ADAPTIVE, timeout=5.0)
        if r.status_code == 200:
            results["adaptive"] = r.json()
    except Exception:
        pass
    try:
        r = await client.get(METRICS_QUEUES, timeout=5.0)
        if r.status_code == 200:
            results["queues"] = r.json()
    except Exception:
        pass
    try:
        r = await client.get(METRICS_WORKERS, timeout=5.0)
        if r.status_code == 200:
            results["workers"] = r.json()
    except Exception:
        pass
    return results


async def run_phase(
    name: str,
    rate: float,
    duration: float,
    concurrency: int,
    http_client: httpx.AsyncClient,
    cumulative_shed_base: Dict[str, int],
) -> PhaseSnapshot:
    """Run one traffic phase, return snapshot."""

    snapshot = PhaseSnapshot(
        phase_name=name,
        target_rate=rate,
        duration_s=duration,
    )

    factory = EventFactory()
    profile = SteadyProfile(name=f"stress_{name}", baseline_rate=rate)
    sink    = AsyncSink(http_client)
    gen     = TrafficGenerator(
        profile=profile,
        factory=factory,
        sink=sink,
        batch_size=50,
        concurrency=concurrency,
    )

    await gen.start()
    print(f"  ▶  {name:12s}  rate={rate:6.0f} ev/s  concurrency={concurrency}", flush=True)

    poll_interval = 2.0
    polls: List[Dict] = []
    deadline = time.monotonic() + duration

    while time.monotonic() < deadline:
        await asyncio.sleep(min(poll_interval, max(0.1, deadline - time.monotonic())))
        m = await poll_metrics(http_client)
        if m:
            polls.append(m)
        # Progress
        remaining = deadline - time.monotonic()
        if remaining > 0:
            ps = m.get("adaptive", {}).get("metrics", {}).get("pressureScore", 0)
            pst = m.get("adaptive", {}).get("metrics", {}).get("pressureState", "?")
            print(f"     {remaining:4.0f}s left  pressureScore={ps:.3f}  state={pst}", flush=True)

    await gen.stop()

    # Last poll for final state
    final = await poll_metrics(http_client)
    if final:
        polls.append(final)

    # Aggregate from polls
    if polls:
        scores = [p.get("adaptive", {}).get("metrics", {}).get("pressureScore", 0) for p in polls]
        snapshot.pressure_score_min = min(scores)
        snapshot.pressure_score_max = max(scores)
        snapshot.pressure_score_end = scores[-1]
        snapshot.pressure_state = polls[-1].get("adaptive", {}).get("metrics", {}).get("pressureState", "NORMAL")
        snapshot.avg_latency_ms = polls[-1].get("adaptive", {}).get("metrics", {}).get("latency", 0.0)
        snapshot.processing_rate = polls[-1].get("adaptive", {}).get("metrics", {}).get("throughput", 0.0)

        q = polls[-1].get("queues", {})
        snapshot.q_critical    = q.get("critical", 0)
        snapshot.q_normal      = q.get("normal", 0)
        snapshot.q_best_effort = q.get("best_effort", 0)

        w = polls[-1].get("workers", {})
        allocs = w.get("allocation", {})
        snapshot.w_critical    = allocs.get("CRITICAL", allocs.get("critical", 0))
        snapshot.w_normal      = allocs.get("NORMAL",   allocs.get("normal", 0))
        snapshot.w_best_effort = allocs.get("BEST_EFFORT", allocs.get("best_effort", 0))

        # Infer actions from last recent events
        recent = polls[-1].get("adaptive", {}).get("recentEvents", [])
        for ev in reversed(recent):
            tier   = ev.get("tier", "")
            status = ev.get("status", "")
            if tier == "NORMAL"      and snapshot.normal_action == "STREAM":
                snapshot.normal_action = status
            if tier == "BEST_EFFORT" and snapshot.be_action == "STREAM":
                snapshot.be_action = status

        shed = polls[-1].get("adaptive", {}).get("shedStats", {})
        # compute delta against base
        snapshot.sampled         = shed.get("sampled", 0)         - cumulative_shed_base.get("sampled", 0)
        snapshot.sampled_kept    = shed.get("sampled_kept", 0)    - cumulative_shed_base.get("sampled_kept", 0)
        snapshot.sampled_dropped = shed.get("sampled_dropped", 0) - cumulative_shed_base.get("sampled_dropped", 0)
        snapshot.shed            = shed.get("shed", 0)            - cumulative_shed_base.get("shed", 0)
        snapshot.deferred        = shed.get("deferred", 0)        - cumulative_shed_base.get("deferred", 0)
        # Update base for next phase
        cumulative_shed_base.update(shed)

    stats = gen.stats()
    snapshot.events_sent      = stats.events_generated
    snapshot.generator_errors = stats.errors

    return snapshot


def print_table(snapshots: List[PhaseSnapshot]) -> None:
    """Print a formatted table of phase results."""
    W = 14
    header_cols = [
        "Phase", "Rate", "PScore-min", "PScore-max", "PScore-end", "PState",
        "Q-CRIT", "Q-NORM", "Q-BE",
        "W-CRIT", "W-NORM", "W-BE",
        "Latency-ms", "ProcRate",
        "NORM-act", "BE-act",
        "Sampled", "Kept", "Dropped", "Shed", "Deferred",
        "Sent", "Errors",
    ]
    sep = "-" * (W * len(header_cols))
    print("\n" + sep)
    print("  PulseFlow Adaptive Stress Test Results")
    print(sep)
    row_fmt = "{:<14}" * len(header_cols)
    print(row_fmt.format(*header_cols))
    print(sep)
    for s in snapshots:
        print(row_fmt.format(
            s.phase_name[:13],
            f"{s.target_rate:.0f}",
            f"{s.pressure_score_min:.3f}",
            f"{s.pressure_score_max:.3f}",
            f"{s.pressure_score_end:.3f}",
            s.pressure_state[:13],
            s.q_critical, s.q_normal, s.q_best_effort,
            s.w_critical, s.w_normal, s.w_best_effort,
            f"{s.avg_latency_ms:.1f}",
            f"{s.processing_rate:.0f}",
            s.normal_action[:13],
            s.be_action[:13],
            s.sampled, s.sampled_kept, s.sampled_dropped,
            s.shed, s.deferred,
            s.events_sent, s.generator_errors,
        ))
    print(sep)


async def main(base_rate: float, duration: float, concurrency: int) -> None:
    phases = [
        ("1x-baseline",  base_rate * 1),
        ("5x-medium",    base_rate * 5),
        ("10x-high",     base_rate * 10),
        ("20x-spike",    base_rate * 20),
        ("1x-recovery",  base_rate * 1),
    ]

    print(f"\nPulseFlow Adaptive Stress Test")
    print(f"  Base rate:   {base_rate} ev/s")
    print(f"  Concurrency: {concurrency} producers")
    print(f"  Phase dur:   {duration}s each")
    print(f"  Phases:      {[p[0] for p in phases]}")

    # Verify pipeline is reachable
    async with httpx.AsyncClient() as probe:
        try:
            r = await probe.get(f"{PIPELINE_BASE}/health", timeout=5.0)
            print(f"\nPipeline: {PIPELINE_BASE}  → HTTP {r.status_code}")
        except Exception as e:
            print(f"\n[ERROR] Pipeline not reachable at {PIPELINE_BASE}: {e}")
            sys.exit(1)

    snapshots: List[PhaseSnapshot] = []
    cumulative_shed_base: Dict[str, int] = {}

    # One persistent HTTP client for all phases (connection pool)
    async with httpx.AsyncClient() as client:
        for phase_name, rate in phases:
            print(f"\n{'='*60}")
            snap = await run_phase(
                name=phase_name,
                rate=rate,
                duration=duration,
                concurrency=concurrency,
                http_client=client,
                cumulative_shed_base=cumulative_shed_base,
            )
            snapshots.append(snap)
            print(f"  ✓ {phase_name} complete  sent={snap.events_sent}  errs={snap.generator_errors}")

        print(f"\n{'='*60}")
        print("Waiting 3s for pipeline to settle before recovery metrics...")
        await asyncio.sleep(3)

    print_table(snapshots)
    print("\nStress test complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PulseFlow adaptive stress test")
    parser.add_argument("--base-rate",   type=float, default=DEFAULT_BASE_RATE,
                        help="Baseline event rate (1x). Default: 100 ev/s")
    parser.add_argument("--duration",    type=float, default=DEFAULT_PHASE_SEC,
                        help="Duration per phase in seconds. Default: 20")
    parser.add_argument("--concurrency", type=int,   default=DEFAULT_CONCURRENCY,
                        help="Number of concurrent producer tasks. Default: 4")
    args = parser.parse_args()

    asyncio.run(main(
        base_rate=args.base_rate,
        duration=args.duration,
        concurrency=args.concurrency,
    ))

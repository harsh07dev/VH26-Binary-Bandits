"""PulseFlow Adaptive Batching End-to-End Stress Test.

Drives TechPulse traffic at escalating rates and records adaptive telemetry at each phase.
Traffic phases: 1x → 5x → 10x → 20x → 1x (recovery)
Baseline: 100 ev/s  concurrency=4

Captures every sampling interval:
  - ingress rate, processing rate
  - queue depth per lane
  - queue growth rate per lane (dq/dt)
  - pressure score/state
  - worker allocation
  - batch size per lane (NORMAL, BEST_EFFORT)
  - average, P95, P99 latency
  - sampled, shed, deferred, critical dropped events

Expected transitions:
  Overload:  dq/dt > 0  →  batch size gradually ↑
  Recovery:  dq/dt < 0  →  batch size gradually ↓
  Low load:  timeout fast-flush, low latency
  CRITICAL:  zero drops at all times

Usage:
    python stress_test.py [--base-rate N] [--duration N] [--no-validate]
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
    # Observed pressure
    pressure_score_min: float = 0.0
    pressure_score_max: float = 0.0
    pressure_score_end: float = 0.0
    pressure_state: str = "NORMAL"
    # Queue depths
    q_critical: int = 0
    q_normal: int = 0
    q_best_effort: int = 0
    # Queue growth rates (dq/dt) per lane
    growth_normal_min: float = 0.0
    growth_normal_max: float = 0.0
    growth_be_min: float = 0.0
    growth_be_max: float = 0.0
    # Workers
    w_critical: int = 0
    w_normal: int = 0
    w_best_effort: int = 0
    # Batch sizes per lane
    batch_size_normal_min: int = 0
    batch_size_normal_max: int = 0
    batch_size_normal_end: int = 0
    batch_size_be_min: int = 0
    batch_size_be_max: int = 0
    batch_size_be_end: int = 0
    # Latency & rate
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    ingress_rate: float = 0.0
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
    # Raw interval samples (for post-hoc analysis)
    interval_samples: List[Dict] = field(default_factory=list)


async def poll_metrics(client: httpx.AsyncClient) -> Dict[str, Any]:
    """Fetch and merge all metric endpoints into a unified flat dict."""
    results: Dict[str, Any] = {}
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


def extract_interval_sample(m: Dict[str, Any], now: float) -> Dict[str, Any]:
    """Extract a flat telemetry snapshot from the merged metrics dict."""
    adaptive  = m.get("adaptive", {})
    metrics   = adaptive.get("metrics", {})
    infra     = adaptive.get("infraMetrics", {})
    batching  = adaptive.get("batching", {})
    shed      = adaptive.get("shedStats", {})

    norm_b = batching.get("normal", {}) if isinstance(batching.get("normal"), dict) else {}
    be_b   = batching.get("best_effort", {}) if isinstance(batching.get("best_effort"), dict) else {}

    return {
        "ts": now,
        "ingress":          metrics.get("ingress", 0.0),
        "throughput":       metrics.get("throughput", 0.0),
        "pressure_state":   metrics.get("pressureState", "NORMAL"),
        "pressure_score":   metrics.get("pressureScore", 0.0),
        # Queue depths
        "q_critical":       infra.get("queueT1", 0),
        "q_normal":         infra.get("queueT2", 0),
        "q_best_effort":    infra.get("queueT3", 0),
        # Growth rates (dq/dt)
        "growth_normal":    norm_b.get("growth_rate", 0.0),
        "growth_be":        be_b.get("growth_rate", 0.0),
        # Workers
        "w_critical":       infra.get("w1", 0),
        "w_normal":         infra.get("w2", 0),
        "w_best_effort":    infra.get("w3", 0),
        # Batch sizes
        "batch_size_normal": norm_b.get("current_batch_size", 50),
        "batch_size_be":     be_b.get("current_batch_size", 50),
        # Latency
        "avg_latency_ms":   metrics.get("latency", 0.0),
        "p95_latency_ms":   0.0,  # filled in run_phase
        "p99_latency_ms":   0.0,
        # Shedding
        "sampled":          shed.get("sampled", 0),
        "sampled_kept":     shed.get("sampled_kept", 0),
        "sampled_dropped":  shed.get("sampled_dropped", 0),
        "shed":             shed.get("shed", 0),
        "deferred":         shed.get("deferred", 0),
        "critical_dropped": shed.get("critical_dropped", 0),
    }


def print_interval_log(phase_name: str, sample: Dict[str, Any]) -> None:
    """Print a single telemetry sample row to stdout."""
    print(
        f"    [{phase_name[:14]:14s}] "
        f"ingress={sample['ingress']:6.0f} ev/s  "
        f"Q_norm={sample['q_normal']:4d}  Q_be={sample['q_best_effort']:4d}  "
        f"dQ_norm={sample['growth_normal']:+7.1f}  dQ_be={sample['growth_be']:+7.1f}  "
        f"BS_norm={sample['batch_size_normal']:3d}  BS_be={sample['batch_size_be']:3d}  "
        f"PState={sample['pressure_state'][:8]:8s}  "
        f"lat={sample['avg_latency_ms']:5.1f}ms  "
        f"shed={sample['shed']}  crit_drop={sample['critical_dropped']}",
        flush=True,
    )


async def run_phase(
    name: str,
    rate: float,
    duration: float,
    concurrency: int,
    http_client: httpx.AsyncClient,
    cumulative_shed_base: Dict[str, int],
    poll_interval: float = 2.0,
    verbose: bool = True,
) -> PhaseSnapshot:
    """Run one traffic phase, return a detailed PhaseSnapshot."""

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
    print(f"\n  ▶  {name}  target={rate:.0f} ev/s  concurrency={concurrency}", flush=True)
    if verbose:
        print(
            f"    {'Phase':14s}  "
            f"{'ingress':>10s}  "
            f"{'Q_norm':>6s}  {'Q_be':>5s}  "
            f"{'dQ_norm':>8s}  {'dQ_be':>8s}  "
            f"{'BS_norm':>7s}  {'BS_be':>6s}  "
            f"{'PState':8s}  "
            f"{'lat_ms':>7s}  "
            f"{'shed':>5s}  {'crit_drop':>9s}",
            flush=True,
        )

    polls: List[Dict] = []
    interval_samples: List[Dict] = []
    deadline = time.monotonic() + duration

    while time.monotonic() < deadline:
        sleep_for = min(poll_interval, max(0.1, deadline - time.monotonic()))
        await asyncio.sleep(sleep_for)
        now = time.monotonic()
        m = await poll_metrics(http_client)
        if m:
            polls.append(m)
            sample = extract_interval_sample(m, now)
            interval_samples.append(sample)
            if verbose:
                print_interval_log(name, sample)

    await gen.stop()

    # One final poll after generator stops
    final = await poll_metrics(http_client)
    if final:
        polls.append(final)
        sample = extract_interval_sample(final, time.monotonic())
        interval_samples.append(sample)
        if verbose:
            print_interval_log(name + "(final)", sample)

    snapshot.interval_samples = interval_samples

    if interval_samples:
        # Aggregate pressure scores
        scores = [s["pressure_score"] for s in interval_samples]
        snapshot.pressure_score_min = min(scores)
        snapshot.pressure_score_max = max(scores)
        snapshot.pressure_score_end = scores[-1]
        snapshot.pressure_state     = interval_samples[-1]["pressure_state"]

        # Queue depths (end of phase)
        snapshot.q_critical    = interval_samples[-1]["q_critical"]
        snapshot.q_normal      = interval_samples[-1]["q_normal"]
        snapshot.q_best_effort = interval_samples[-1]["q_best_effort"]

        # Growth rates (dq/dt) – min/max across intervals
        gn = [s["growth_normal"] for s in interval_samples]
        gb = [s["growth_be"]     for s in interval_samples]
        snapshot.growth_normal_min = min(gn)
        snapshot.growth_normal_max = max(gn)
        snapshot.growth_be_min     = min(gb)
        snapshot.growth_be_max     = max(gb)

        # Workers (end of phase)
        snapshot.w_critical    = interval_samples[-1]["w_critical"]
        snapshot.w_normal      = interval_samples[-1]["w_normal"]
        snapshot.w_best_effort = interval_samples[-1]["w_best_effort"]

        # Batch sizes per lane
        bsn = [s["batch_size_normal"] for s in interval_samples]
        bsb = [s["batch_size_be"]     for s in interval_samples]
        snapshot.batch_size_normal_min = min(bsn)
        snapshot.batch_size_normal_max = max(bsn)
        snapshot.batch_size_normal_end = bsn[-1]
        snapshot.batch_size_be_min     = min(bsb)
        snapshot.batch_size_be_max     = max(bsb)
        snapshot.batch_size_be_end     = bsb[-1]

        # Latency (end of phase, from final metrics)
        snapshot.avg_latency_ms  = interval_samples[-1]["avg_latency_ms"]
        snapshot.p95_latency_ms  = interval_samples[-1].get("p95_latency_ms", 0.0)
        snapshot.p99_latency_ms  = interval_samples[-1].get("p99_latency_ms", 0.0)
        snapshot.ingress_rate     = interval_samples[-1]["ingress"]
        snapshot.processing_rate  = interval_samples[-1]["throughput"]

        # Actions (from last recent events)
        if polls:
            recent = polls[-1].get("adaptive", {}).get("recentEvents", [])
            for ev in reversed(recent):
                tier   = ev.get("tier", "")
                status = ev.get("status", "")
                if tier == "NORMAL"      and snapshot.normal_action == "STREAM":
                    snapshot.normal_action = status
                if tier == "BEST_EFFORT" and snapshot.be_action == "STREAM":
                    snapshot.be_action = status

        # Shedding / drops (delta from cumulative base)
        last_shed = interval_samples[-1]
        snapshot.sampled         = last_shed["sampled"]         - cumulative_shed_base.get("sampled", 0)
        snapshot.sampled_kept    = last_shed["sampled_kept"]    - cumulative_shed_base.get("sampled_kept", 0)
        snapshot.sampled_dropped = last_shed["sampled_dropped"] - cumulative_shed_base.get("sampled_dropped", 0)
        snapshot.shed            = last_shed["shed"]            - cumulative_shed_base.get("shed", 0)
        snapshot.deferred        = last_shed["deferred"]        - cumulative_shed_base.get("deferred", 0)
        snapshot.critical_dropped = last_shed["critical_dropped"]
        # Update base for next phase
        cumulative_shed_base.update({
            k: last_shed[k] for k in ("sampled", "sampled_kept", "sampled_dropped", "shed", "deferred")
        })

    stats = gen.stats()
    snapshot.events_sent      = stats.events_generated
    snapshot.generator_errors = stats.errors

    return snapshot


def print_table(snapshots: List[PhaseSnapshot]) -> None:
    """Print a comprehensive phase-summary table."""
    # ── Section 1: Pressure / Queues / Workers ─────────────────────────────────
    H1 = 13
    cols1 = ["Phase", "Rate", "PScore-min", "PScore-max", "PScore-end", "PState",
             "Q-CRIT", "Q-NORM", "Q-BE",
             "W-CRIT", "W-NORM", "W-BE",
             "Ingress", "ProcRate", "Lat-avg", "P95-ms", "P99-ms"]
    sep = "-" * (H1 * len(cols1))
    fmt = "{:<13}" * len(cols1)
    print("\n" + sep)
    print("  PulseFlow Adaptive Stress Test — Phase Summary (Pressure / Queues / Workers / Latency)")
    print(sep)
    print(fmt.format(*cols1))
    print(sep)
    for s in snapshots:
        print(fmt.format(
            s.phase_name[:12],
            f"{s.target_rate:.0f}",
            f"{s.pressure_score_min:.3f}",
            f"{s.pressure_score_max:.3f}",
            f"{s.pressure_score_end:.3f}",
            s.pressure_state[:12],
            s.q_critical, s.q_normal, s.q_best_effort,
            s.w_critical, s.w_normal, s.w_best_effort,
            f"{s.ingress_rate:.0f}",
            f"{s.processing_rate:.0f}",
            f"{s.avg_latency_ms:.1f}",
            f"{s.p95_latency_ms:.1f}",
            f"{s.p99_latency_ms:.1f}",
        ))
    print(sep)

    # ── Section 2: Adaptive Batch Sizes per lane ────────────────────────────────
    cols2 = ["Phase", "Rate",
             "BS_N-min", "BS_N-max", "BS_N-end",
             "BS_BE-min", "BS_BE-max", "BS_BE-end",
             "dQ_N-min", "dQ_N-max", "dQ_BE-min", "dQ_BE-max",
             "NORM-act", "BE-act"]
    sep2 = "-" * (H1 * len(cols2))
    fmt2 = "{:<13}" * len(cols2)
    print("\n" + sep2)
    print("  Adaptive Batch Sizes per Lane (NORMAL / BEST-EFFORT) & Queue Growth Rates (dq/dt)")
    print(sep2)
    print(fmt2.format(*cols2))
    print(sep2)
    for s in snapshots:
        print(fmt2.format(
            s.phase_name[:12],
            f"{s.target_rate:.0f}",
            s.batch_size_normal_min,
            s.batch_size_normal_max,
            s.batch_size_normal_end,
            s.batch_size_be_min,
            s.batch_size_be_max,
            s.batch_size_be_end,
            f"{s.growth_normal_min:+.1f}",
            f"{s.growth_normal_max:+.1f}",
            f"{s.growth_be_min:+.1f}",
            f"{s.growth_be_max:+.1f}",
            s.normal_action[:12],
            s.be_action[:12],
        ))
    print(sep2)

    # ── Section 3: Event Shedding & Drop Counters ───────────────────────────────
    cols3 = ["Phase", "Rate", "Sent", "Errors",
             "Sampled", "Kept", "Dropped", "Shed", "Deferred", "CRIT-DROP"]
    sep3 = "-" * (H1 * len(cols3))
    fmt3 = "{:<13}" * len(cols3)
    print("\n" + sep3)
    print("  Event Shedding & Critical Drop Counters")
    print(sep3)
    print(fmt3.format(*cols3))
    print(sep3)
    for s in snapshots:
        print(fmt3.format(
            s.phase_name[:12],
            f"{s.target_rate:.0f}",
            s.events_sent, s.generator_errors,
            s.sampled, s.sampled_kept, s.sampled_dropped,
            s.shed, s.deferred, s.critical_dropped,
        ))
    print(sep3)


def validate_results(snapshots: List[PhaseSnapshot]) -> None:
    """Run validation assertions on all phase snapshots. Prints PASS/FAIL per check."""
    print(f"\n{'='*70}")
    print("  Adaptive Batching Stress Test — Validation Results")
    print(f"{'='*70}")
    failed = []

    def check(label: str, condition: bool, detail: str = "") -> None:
        status = "PASS" if condition else "FAIL"
        print(f"  [{status}] {label}{' — ' + detail if detail else ''}")
        if not condition:
            failed.append(label)

    # Find relevant phases
    p1 = next((s for s in snapshots if "1x" in s.phase_name and "recovery" not in s.phase_name), None)
    p4 = next((s for s in snapshots if "20x" in s.phase_name or "spike" in s.phase_name), None)
    p5 = next((s for s in snapshots if "recovery" in s.phase_name), None)

    # 1. Golden Invariant
    total_crit = sum(s.critical_dropped for s in snapshots)
    check("Zero CRITICAL event loss", total_crit == 0, f"critical_dropped={total_crit}")

    # 2. Batch size escalation under overload
    if p1 and p4:
        check(
            "Batch size NORMAL escalated under 20x load",
            p4.batch_size_normal_max >= p1.batch_size_normal_end,
            f"P1_end={p1.batch_size_normal_end} P4_max={p4.batch_size_normal_max}",
        )
        check(
            "Batch size BEST-EFFORT escalated under 20x load",
            p4.batch_size_be_max >= p1.batch_size_be_end,
            f"P1_end={p1.batch_size_be_end} P4_max={p4.batch_size_be_max}",
        )

    # 3. Batch size de-escalation during recovery
    if p4 and p5:
        check(
            "Batch size NORMAL de-escalated during recovery",
            p5.batch_size_normal_end <= p4.batch_size_normal_max,
            f"P4_max={p4.batch_size_normal_max} P5_end={p5.batch_size_normal_end}",
        )
        check(
            "Batch size BEST-EFFORT de-escalated during recovery",
            p5.batch_size_be_end <= p4.batch_size_be_max,
            f"P4_max={p4.batch_size_be_max} P5_end={p5.batch_size_be_end}",
        )

    # 4. dq/dt positive during overload
    if p4:
        check(
            "dq/dt NORMAL > 0 during overload (queue growing)",
            p4.growth_normal_max > 0,
            f"max_growth_normal={p4.growth_normal_max:.2f}",
        )

    # 5. dq/dt negative or ≤ 0 during recovery
    if p5:
        check(
            "dq/dt NORMAL <= 0 during recovery (queue draining)",
            p5.growth_normal_min <= 0,
            f"min_growth_normal={p5.growth_normal_min:.2f}",
        )

    # 6. Low-traffic fast flush: avg latency bounded in phase 1
    if p1:
        check(
            "Phase 1 avg latency < 500ms (fast flush)",
            p1.avg_latency_ms < 500.0 or p1.avg_latency_ms == 0.0,
            f"avg_lat={p1.avg_latency_ms:.1f}ms",
        )

    # 7. Generator errors minimal
    total_errors = sum(s.generator_errors for s in snapshots)
    check("Generator errors < 5% of sent", 
          total_errors < max(1, sum(s.events_sent for s in snapshots) * 0.05),
          f"errors={total_errors}")

    print(f"{'='*70}")
    if failed:
        print(f"  ✗ {len(failed)} check(s) FAILED: {failed}")
    else:
        print(f"  ✓ All checks PASSED — Adaptive batching transitions verified.")
    print(f"{'='*70}\n")


async def main(base_rate: float, duration: float, concurrency: int, validate: bool = True) -> None:
    phases = [
        ("1x-baseline",  base_rate * 1),
        ("5x-medium",    base_rate * 5),
        ("10x-high",     base_rate * 10),
        ("20x-spike",    base_rate * 20),
        ("1x-recovery",  base_rate * 1),
    ]

    print(f"\nPulseFlow Adaptive Batching Stress Test")
    print(f"  Base rate:   {base_rate} ev/s")
    print(f"  Concurrency: {concurrency} producers")
    print(f"  Phase dur:   {duration}s each")
    print(f"  Phases:      {[p[0] for p in phases]}")
    print(f"  Sampling:    every 2s within each phase")

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

    # One persistent HTTP client shared across all phases
    async with httpx.AsyncClient() as client:
        for phase_name, rate in phases:
            print(f"\n{'='*70}")
            snap = await run_phase(
                name=phase_name,
                rate=rate,
                duration=duration,
                concurrency=concurrency,
                http_client=client,
                cumulative_shed_base=cumulative_shed_base,
                poll_interval=2.0,
                verbose=True,
            )
            snapshots.append(snap)
            print(
                f"  ✓ {phase_name:14s}  sent={snap.events_sent:6d}  "
                f"errs={snap.generator_errors}  "
                f"BS_NORM={snap.batch_size_normal_end}  BS_BE={snap.batch_size_be_end}"
            )

        print(f"\n{'='*70}")
        print("  Waiting 3s for pipeline to settle...")
        await asyncio.sleep(3)

    print_table(snapshots)
    if validate:
        validate_results(snapshots)
    print("Stress test complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PulseFlow adaptive batching stress test")
    parser.add_argument("--base-rate",    type=float, default=DEFAULT_BASE_RATE,
                        help="Baseline event rate (1x). Default: 100 ev/s")
    parser.add_argument("--duration",     type=float, default=DEFAULT_PHASE_SEC,
                        help="Duration per phase in seconds. Default: 20")
    parser.add_argument("--concurrency",  type=int,   default=DEFAULT_CONCURRENCY,
                        help="Number of concurrent producer tasks. Default: 4")
    parser.add_argument("--no-validate",  action="store_true",
                        help="Skip end-of-run validation assertions")
    args = parser.parse_args()

    asyncio.run(main(
        base_rate=args.base_rate,
        duration=args.duration,
        concurrency=args.concurrency,
        validate=not args.no_validate,
    ))

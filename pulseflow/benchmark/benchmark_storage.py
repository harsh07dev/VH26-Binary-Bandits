"""PulseFlow Benchmark: Result Storage and Persistence.

Persists benchmark records to disk in JSON format under benchmark/results/history/.
Ensures historical runs are preserved and easily queryable by the dashboard and jury.
"""

from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any, Dict, List, Optional


HISTORY_DIR = Path(__file__).parent / "results" / "history"
INDEX_FILE = HISTORY_DIR / "index.json"


def _ensure_history_dir() -> Path:
    """Ensure the history directory exists."""
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    return HISTORY_DIR


def save_benchmark_result(result: Dict[str, Any]) -> str:
    """Save benchmark result to disk and update index.
    
    Returns the benchmark_id.
    """
    _ensure_history_dir()
    bench_id = result.get("benchmark_id")
    if not bench_id:
        bench_id = f"benchmark_{int(time.time())}_{time.strftime('%Y%m%d_%H%M%S')}"
        result["benchmark_id"] = bench_id

    file_path = HISTORY_DIR / f"{bench_id}.json"
    file_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    # Update index
    index_entries = _read_index()
    
    # Summary entry for quick listing
    summary = {
        "benchmark_id": bench_id,
        "timestamp": result.get("timestamp", time.time()),
        "created_at": result.get("created_at", time.strftime("%Y-%m-%d %H:%M:%S UTC")),
        "scenario": result.get("workload", {}).get("scenario", "UNKNOWN"),
        "event_count": result.get("workload", {}).get("total_events", 0),
        "target_rate": result.get("workload", {}).get("target_rate", 0),
        "seed": result.get("workload", {}).get("seed", 42),
        "naive_critical_loss": result.get("naive", {}).get("critical_failed", 0),
        "pulseflow_critical_loss": result.get("pulseflow", {}).get("critical_failed", 0),
        "critical_p95_improvement_pct": result.get("advantage", {}).get("critical_p95_improvement_pct", 0.0),
    }

    # Filter out if already in index
    index_entries = [e for e in index_entries if e.get("benchmark_id") != bench_id]
    index_entries.insert(0, summary)  # newest first

    INDEX_FILE.write_text(json.dumps(index_entries, indent=2), encoding="utf-8")
    return bench_id


def _read_index() -> List[Dict[str, Any]]:
    """Read the benchmark index file."""
    if not INDEX_FILE.exists():
        return []
    try:
        data = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        return []
    except Exception:
        return []


def list_benchmark_results(limit: int = 50) -> List[Dict[str, Any]]:
    """Return summary metadata for past benchmark executions, ordered newest first."""
    _ensure_history_dir()
    entries = _read_index()
    if not entries:
        # Re-index if files exist on disk
        rebuilt = []
        for file in sorted(HISTORY_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
            if file.name == "index.json":
                continue
            try:
                res = json.loads(file.read_text(encoding="utf-8"))
                rebuilt.append({
                    "benchmark_id": res.get("benchmark_id", file.stem),
                    "timestamp": res.get("timestamp", file.stat().st_mtime),
                    "created_at": res.get("created_at", ""),
                    "scenario": res.get("workload", {}).get("scenario", "UNKNOWN"),
                    "event_count": res.get("workload", {}).get("total_events", 0),
                    "target_rate": res.get("workload", {}).get("target_rate", 0),
                    "seed": res.get("workload", {}).get("seed", 42),
                    "naive_critical_loss": res.get("naive", {}).get("critical_failed", 0),
                    "pulseflow_critical_loss": res.get("pulseflow", {}).get("critical_failed", 0),
                    "critical_p95_improvement_pct": res.get("advantage", {}).get("critical_p95_improvement_pct", 0.0),
                })
            except Exception:
                continue
        INDEX_FILE.write_text(json.dumps(rebuilt, indent=2), encoding="utf-8")
        entries = rebuilt

    return entries[:limit]


def get_benchmark_result(benchmark_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve full normalized benchmark result JSON by ID."""
    _ensure_history_dir()
    file_path = HISTORY_DIR / f"{benchmark_id}.json"
    if not file_path.exists():
        return None
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return None

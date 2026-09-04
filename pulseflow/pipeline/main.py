"""PulseFlow pipeline: Main Backend Application.

Entry point orchestrating FastAPI, Ingestion API, QueueManager, WorkerPool, and SQLite storage.
Handles graceful startup and shutdown lifecycles.
"""

from contextlib import asynccontextmanager
from typing import Any, Dict
from fastapi import FastAPI
import uvicorn

from contracts.metrics import QueueMetrics, WorkerMetrics
from contracts.priorities import Priority
from pipeline.config import config
from pipeline.storage.database import database_manager
from pipeline.queues.queue_manager import queue_manager
from pipeline.workers.worker_pool import worker_pool
from pipeline.ingestion.api import router as ingestion_router, set_enqueue_handler


import time
from collections import deque
from typing import Any, Deque, Dict, Optional, Tuple


class RateTracker:
    """Sliding-window tracker measuring real-time incoming event ingress rate (events/sec)."""

    def __init__(self, window_sec: float = 1.0):
        self.window_sec = float(window_sec)
        self.count = 0
        self.total_count = 0
        self.last_reset = time.time()
        self._samples: Deque[Tuple[float, int]] = deque()

    def reset(self) -> None:
        """Reset all counters and rolling samples."""
        self.count = 0
        self.total_count = 0
        self.last_reset = time.time()
        self._samples.clear()

    def mark(self, count: int = 1, now: Optional[float] = None) -> float:
        """Record incoming event(s) and return the current ingress rate."""
        t = now if now is not None else time.time()
        self.count += count
        self.total_count += count
        self._samples.append((t, count))
        self._prune(t)
        return self.get_rate(now=t)

    def _prune(self, current_time: float) -> None:
        """Prune samples older than the sliding window."""
        cutoff = current_time - self.window_sec
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()

    def get_rate(self, now: Optional[float] = None) -> float:
        """Return the current actual ingress rate (events/sec) over the active window."""
        t = now if now is not None else time.time()
        self._prune(t)
        if not self._samples:
            return 0.0
        total_in_window = sum(s[1] for s in self._samples)
        earliest = self._samples[0][0]
        elapsed = t - earliest
        effective_window = max(1.0, min(self.window_sec, elapsed))
        return round(total_in_window / effective_window, 2)

    @property
    def current_rate(self) -> float:
        return self.get_rate()


rate_tracker = RateTracker(window_sec=5.0)   # 5s window keeps spike bursts visible for full TechPulse send cycle
_rate_tracker = rate_tracker


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Orchestrate pipeline startup and graceful shutdown sequences."""
    # --- 1. Startup Sequence ---
    # a. Initialize Database schema and indexes
    await database_manager.init_db()

    from pipeline.ingestion.api import set_enqueue_handler
    from contracts.metrics import SystemSnapshot
    from adaptive.scheduler.decision_engine import DecisionEngine
    from adaptive.scheduler.metrics_tracker import adaptive_metrics
    from pipeline.processing.telemetry import processing_telemetry
    from contracts.priorities import Priority
    from contracts.events import Event

    async def adaptive_enqueue(event: Event, priority: Priority) -> None:
        rate = rate_tracker.mark()
        
        # Pull actual system metrics
        q_metrics = queue_manager.queue_metrics()
        w_metrics = worker_pool.worker_metrics()
        
        avg_lat = processing_telemetry.get_avg_latency_ms()
        proc_rate = processing_telemetry.get_processing_rate()
        p95_lat, p99_lat = processing_telemetry.get_percentiles()
        
        snapshot = SystemSnapshot(
            queues=q_metrics,
            workers=w_metrics,
            incoming_count=rate_tracker.total_count,
            processed_count=processing_telemetry.get_processed_count(),
            avg_latency_ms=avg_lat,
            processing_rate=proc_rate,
            p95_latency_ms=p95_lat,
            p99_latency_ms=p99_lat,
        )
        decision = await DecisionEngine.process_event(event, snapshot, ingress_rate=rate)
        
        # Inject the real event type into the tracker
        adaptive_metrics.record_decision(decision)
        if len(adaptive_metrics.recent_events) > 0:
            adaptive_metrics.recent_events[-1]["type"] = event.event_type

    set_enqueue_handler(adaptive_enqueue)

    # c. Start WorkerPool with configured allocations
    await worker_pool.start(
        initial_allocation=config.default_allocation,
        batch_sizes={
            lane: config.batch_size for lane in config.default_allocation
        },
        batch_timeouts_ms={
            lane: config.batch_timeout_ms for lane in config.default_allocation
        },
    )

    yield

    # --- 2. Shutdown Sequence ---
    # a. Stop accepting new events into the queues
    set_enqueue_handler(None)

    # b. Gracefully stop WorkerPool and finish active batches
    await worker_pool.stop()

    # c. Close database connection
    await database_manager.close()


# Core FastAPI Application
app = FastAPI(
    title="PulseFlow Pipeline",
    description="Intelligent Adaptive Event Processing Pipeline - Machine 2 Backend",
    version="0.1.0",
    lifespan=lifespan,
)

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. Ingestion API routes: POST /events, POST /events/batch, GET /health
app.include_router(ingestion_router)


# 2. Metrics & System Observation Endpoints
@app.get("/metrics/queues", response_model=QueueMetrics, tags=["Observability"])
async def get_queue_metrics() -> QueueMetrics:
    """Real-time depths of the three priority queues (CRITICAL, NORMAL, BEST_EFFORT)."""
    return queue_manager.queue_metrics()


@app.get("/metrics/queues/capacities", tags=["Observability"])
async def get_queue_capacities() -> Dict[str, Any]:
    """Configured queue capacities for adaptive pressure calculations (None = unbounded)."""
    return {
        "capacities": queue_manager.capacities(),
        "total_depth": queue_manager.total_depth(),
    }


@app.get("/metrics/workers", response_model=WorkerMetrics, tags=["Observability"])
async def get_worker_metrics() -> WorkerMetrics:
    """Real-time worker allocation, status, and utilization across priority lanes."""
    return worker_pool.worker_metrics()


@app.get("/metrics/adaptive", tags=["Observability"])
async def get_adaptive_metrics() -> Dict[str, Any]:
    """Real-time telemetry from the Adaptive Decision Engine."""
    from adaptive.scheduler.metrics_tracker import adaptive_metrics
    from pipeline.processing.telemetry import processing_telemetry
    
    q_metrics = queue_manager.queue_metrics()
    w_metrics = worker_pool.worker_metrics()
    
    is_spike = False
    processing_cost = "LOW"
    pressure_state = "NORMAL"
    pressure_score = 0.0
    
    avg_lat = processing_telemetry.get_avg_latency_ms()
    proc_rate = processing_telemetry.get_processing_rate()
    actual_ingress_rate = rate_tracker.get_rate()
    
    if adaptive_metrics.latest_decision:
        pressure_state = adaptive_metrics.latest_decision.pressure_state.value
        pressure_score = adaptive_metrics.latest_decision.pressure_score
        is_spike = pressure_state != "NORMAL"
        processing_cost = "HIGH" if pressure_state == "EXTREME" else ("MEDIUM" if pressure_state == "HIGH" else "LOW")
        
    metrics = {
        "queueSize": q_metrics.total_depth,
        "latency": avg_lat,
        "workerLoad": w_metrics.utilization * 100,
        "processingCost": processing_cost,
        "isSpikeMode": is_spike,
        "ingress": actual_ingress_rate,
        "actual_ingress_rate": actual_ingress_rate,
        "ingress_rate": actual_ingress_rate,
        "ingressRate": actual_ingress_rate,
        "throughput": proc_rate,
        "pressureState": pressure_state,
        "pressureScore": pressure_score,
    }
    
    infraMetrics = {
        "queueT1": q_metrics.critical,
        "latT1": processing_telemetry.get_avg_latency_ms(Priority.CRITICAL),
        "queueT2": q_metrics.normal,
        "latT2": processing_telemetry.get_avg_latency_ms(Priority.NORMAL),
        "queueT3": q_metrics.best_effort,
        "latT3": processing_telemetry.get_avg_latency_ms(Priority.BEST_EFFORT),
        "w1": worker_pool.get_allocation()[Priority.CRITICAL],
        "w2": worker_pool.get_allocation()[Priority.NORMAL],
        "w3": worker_pool.get_allocation()[Priority.BEST_EFFORT],
        "w4": 0, # Spare
        "totalWorkers": w_metrics.total,
    }
    
    return {
        "metrics": metrics,
        "infraMetrics": infraMetrics,
        "shedStats": adaptive_metrics.shed_stats,
        "recentEvents": list(adaptive_metrics.recent_events),
        "actual_ingress_rate": actual_ingress_rate,
        "ingress_rate": actual_ingress_rate,
        "ingressRate": actual_ingress_rate,
    }


def main() -> None:
    """Run server directly via Uvicorn."""
    uvicorn.run(
        "pipeline.main:app",
        host=config.host,
        port=config.port,
        reload=False,
    )


if __name__ == "__main__":
    main()

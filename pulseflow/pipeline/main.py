"""PulseFlow pipeline: Main Backend Application.

Entry point orchestrating FastAPI, Ingestion API, QueueManager, WorkerPool, and SQLite storage.
Handles graceful startup and shutdown lifecycles.
"""

from contextlib import asynccontextmanager
from typing import Any, Dict
from fastapi import FastAPI
import uvicorn

from contracts.metrics import QueueMetrics, WorkerMetrics
from pipeline.config import config
from pipeline.storage.database import database_manager
from pipeline.queues.queue_manager import queue_manager
from pipeline.workers.worker_pool import worker_pool
from pipeline.ingestion.api import router as ingestion_router, set_enqueue_handler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Orchestrate pipeline startup and graceful shutdown sequences."""
    # --- 1. Startup Sequence ---
    # a. Initialize Database schema and indexes
    await database_manager.init_db()

    # b. Connect Ingestion to QueueManager
    set_enqueue_handler(queue_manager.enqueue)

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

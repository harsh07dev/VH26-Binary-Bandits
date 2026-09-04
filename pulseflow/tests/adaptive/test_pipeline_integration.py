import pytest
import asyncio
from httpx import AsyncClient

# Import the main FastAPI app so lifespan is triggered
from pipeline.main import app
from pipeline.queues.queue_manager import queue_manager
from pipeline.workers.worker_pool import worker_pool
from contracts.priorities import Priority

@pytest.fixture(autouse=True)
async def cleanup_pool():
    yield
    # Force stop the pool after the test if it's running
    if worker_pool.is_running:
        await worker_pool.stop()


@pytest.mark.asyncio
async def test_adaptive_pipeline_integration():
    """Verify that Adaptive Decisions actually affect processing in real-time."""
    
    # We will use the ASGI app through httpx to trigger the lifespan hook
    # which binds the database, adaptive_enqueue_handler, and starts the worker pool.
    
    from httpx import ASGITransport
    from adaptive.pressure.pressure_config import PressureConfig
    
    # Store original and lower threshold for testing
    orig_high = PressureConfig.HIGH_THRESHOLD
    PressureConfig.HIGH_THRESHOLD = 0.01
    
    try:
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                # 1. NORMAL PRESSURE (Initial State)
                alloc = worker_pool.get_allocation()
                assert alloc[Priority.CRITICAL] == 2
                assert alloc[Priority.NORMAL] == 4
                assert alloc[Priority.BEST_EFFORT] == 2
                
                # 2. TRIGGER HIGH PRESSURE
                events = [{"event_type": "CLICK", "payload": {"foo": "bar"}} for _ in range(250)]
                
                res = await client.post("/events/batch", json=events)
                assert res.status_code == 202
                
                await asyncio.sleep(0.5)
                
                new_alloc = worker_pool.get_allocation()
                assert new_alloc[Priority.CRITICAL] >= 3
                assert new_alloc[Priority.BEST_EFFORT] <= 1
    finally:
        PressureConfig.HIGH_THRESHOLD = orig_high

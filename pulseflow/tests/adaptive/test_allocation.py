import pytest
import asyncio
from contracts.priorities import Priority
from adaptive.pressure.pressure_config import PressureState
from adaptive.allocation.worker_allocator import WorkerAllocator
from pipeline.workers.worker_pool import WorkerPool

@pytest.fixture
def worker_pool():
    # Instantiate a clean worker pool for testing
    pool = WorkerPool()
    return pool

def test_allocation_calculations():
    """Verify desired allocations match the exact requirements."""
    
    # NORMAL
    normal = WorkerAllocator.calculate_desired_allocation(PressureState.NORMAL)
    assert normal[Priority.CRITICAL] == 2
    assert normal[Priority.NORMAL] == 4
    assert normal[Priority.BEST_EFFORT] == 2
    assert sum(normal.values()) == 8
    
    # HIGH
    high = WorkerAllocator.calculate_desired_allocation(PressureState.HIGH)
    assert high[Priority.CRITICAL] == 3
    assert high[Priority.NORMAL] == 4
    assert high[Priority.BEST_EFFORT] == 1
    assert sum(high.values()) == 8
    
    # EXTREME
    extreme = WorkerAllocator.calculate_desired_allocation(PressureState.EXTREME)
    assert extreme[Priority.CRITICAL] == 4
    assert extreme[Priority.NORMAL] == 4
    assert extreme[Priority.BEST_EFFORT] == 0
    assert sum(extreme.values()) == 8


@pytest.mark.asyncio
async def test_worker_pool_application(worker_pool: WorkerPool):
    """Verify desired allocation translates cleanly to actual runtime state."""
    
    # 1. Start with NORMAL pressure
    desired = WorkerAllocator.calculate_desired_allocation(PressureState.NORMAL)
    await worker_pool.start(initial_allocation=desired)
    
    actual = worker_pool.get_allocation()
    assert actual == desired
    
    # 2. Shift to HIGH pressure
    desired = WorkerAllocator.calculate_desired_allocation(PressureState.HIGH)
    await worker_pool.set_allocation(allocation=desired)
    
    actual = worker_pool.get_allocation()
    assert actual == desired
    
    # 3. Shift to EXTREME pressure
    desired = WorkerAllocator.calculate_desired_allocation(PressureState.EXTREME)
    await worker_pool.set_allocation(allocation=desired)
    
    actual = worker_pool.get_allocation()
    assert actual == desired
    
    # Cleanup
    await worker_pool.stop()

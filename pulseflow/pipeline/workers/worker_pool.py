"""PulseFlow pipeline: Worker Pool.

Manages the lifecycle, scaling, and lane assignments of stream and batch workers.
Exposes the dynamic worker reallocation interface for Shrikar's adaptive scheduler
without containing any scheduling heuristics.
"""

import asyncio
from typing import Dict, List, Optional, Union
from contracts.priorities import Priority
from contracts.metrics import WorkerMetrics
from pipeline.queues.queue_manager import QueueManager, queue_manager
from pipeline.processing.event_processor import EventProcessor, event_processor
from pipeline.workers.worker import BaseWorker
from pipeline.workers.stream_worker import StreamWorker
from pipeline.workers.batch_worker import BatchWorker


class WorkerPool:
    """Coordinates worker lifecycle and dynamic allocation across the three priority queues."""

    DEFAULT_ALLOCATION = {
        Priority.CRITICAL: 2,
        Priority.NORMAL: 4,
        Priority.BEST_EFFORT: 2,
    }

    DEFAULT_MODES = {
        Priority.CRITICAL: "STREAM",
        Priority.NORMAL: "BATCH",
        Priority.BEST_EFFORT: "BATCH",
    }

    def __init__(
        self,
        qm: Optional[QueueManager] = None,
        processor: Optional[EventProcessor] = None,
    ) -> None:
        self.queue_manager = qm or queue_manager
        self.processor = processor or event_processor
        self._workers: Dict[Priority, List[BaseWorker]] = {
            Priority.CRITICAL: [],
            Priority.NORMAL: [],
            Priority.BEST_EFFORT: [],
        }
        self._modes: Dict[Priority, str] = dict(self.DEFAULT_MODES)
        self._worker_counter: int = 0
        self._is_running: bool = False
        self._lock: Optional[asyncio.Lock] = None

    def _get_lock(self) -> asyncio.Lock:
        try:
            current_loop = asyncio.get_running_loop()
            if self._lock is not None:
                lock_loop = getattr(self._lock, "_loop", None)
                if lock_loop is not None and (lock_loop.is_closed() or lock_loop is not current_loop):
                    self._lock = None
        except RuntimeError:
            pass
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    @property
    def is_running(self) -> bool:
        """True if the worker pool has been started and is currently operational."""
        return self._is_running

    def _resolve_priority(self, priority: Union[Priority, str]) -> Priority:
        """Helper to resolve Priority enum from string or enum."""
        if isinstance(priority, Priority):
            return priority
        return Priority.from_str(priority)

    def _create_worker(
        self,
        priority: Priority,
        mode: str,
        batch_size: int = 50,
        batch_timeout_ms: float = 100.0,
    ) -> BaseWorker:
        """Factory method to instantiate an appropriate worker for a lane."""
        self._worker_counter += 1
        worker_id = f"{priority.value.lower()}-{self._worker_counter}"
        queue = self.queue_manager.get_queue(priority)

        if mode.upper() == "STREAM":
            return StreamWorker(
                worker_id=worker_id,
                priority=priority,
                queue=queue,
                processor=self.processor,
            )
        else:
            return BatchWorker(
                worker_id=worker_id,
                priority=priority,
                queue=queue,
                processor=self.processor,
                batch_size=batch_size,
                batch_timeout_ms=batch_timeout_ms,
            )

    async def set_allocation(
        self,
        allocation: Dict[Union[Priority, str], int],
        modes: Optional[Dict[Union[Priority, str], str]] = None,
        batch_sizes: Optional[Dict[Union[Priority, str], int]] = None,
        batch_timeouts_ms: Optional[Dict[Union[Priority, str], float]] = None,
    ) -> None:
        """Dynamically scale or adjust worker allocations across priority lanes.
        
        This is the execution interface called by the adaptive engine (worker_allocator).
        """
        async with self._get_lock():
            # Update processing modes if provided
            if modes:
                for k, v in modes.items():
                    p = self._resolve_priority(k)
                    self._modes[p] = v.upper()

            for k, target_count in allocation.items():
                p = self._resolve_priority(k)
                target_count = max(0, target_count)
                current_workers = self._workers[p]
                current_mode = self._modes.get(p, "STREAM" if p == Priority.CRITICAL else "BATCH")
                b_size = (batch_sizes or {}).get(p, 50)
                b_timeout = (batch_timeouts_ms or {}).get(p, 100.0)

                # Check if current workers match the desired mode
                workers_to_keep: List[BaseWorker] = []
                workers_to_retire: List[BaseWorker] = []

                for w in current_workers:
                    is_stream = isinstance(w, StreamWorker)
                    expected_stream = (current_mode == "STREAM")
                    if is_stream == expected_stream:
                        workers_to_keep.append(w)
                        if isinstance(w, BatchWorker):
                            w.set_batch_params(b_size, b_timeout)
                    else:
                        workers_to_retire.append(w)

                # Stop retired workers (e.g. mode changed from STREAM to BATCH)
                for w in workers_to_retire:
                    await w.stop()

                # Scale down if more workers than target
                while len(workers_to_keep) > target_count:
                    retiring = workers_to_keep.pop()
                    await retiring.stop()

                # Scale up if fewer workers than target
                while len(workers_to_keep) < target_count:
                    new_worker = self._create_worker(
                        priority=p,
                        mode=current_mode,
                        batch_size=b_size,
                        batch_timeout_ms=b_timeout,
                    )
                    if self._is_running:
                        new_worker.start()
                    workers_to_keep.append(new_worker)

                self._workers[p] = workers_to_keep

    async def start(
        self,
        initial_allocation: Optional[Dict[Union[Priority, str], int]] = None,
        modes: Optional[Dict[Union[Priority, str], str]] = None,
        batch_sizes: Optional[Dict[Union[Priority, str], int]] = None,
        batch_timeouts_ms: Optional[Dict[Union[Priority, str], float]] = None,
    ) -> None:
        """Start the worker pool and launch all assigned workers."""
        async with self._get_lock():
            if self._is_running:
                return
            self._is_running = True

        alloc = initial_allocation or self.DEFAULT_ALLOCATION
        await self.set_allocation(
            allocation=alloc,
            modes=modes,
            batch_sizes=batch_sizes,
            batch_timeouts_ms=batch_timeouts_ms,
        )

        # Ensure all existing workers are started
        for workers in self._workers.values():
            for w in workers:
                if not w.is_running:
                    w.start()

    async def stop(self, timeout: float = 3.0) -> None:
        """Gracefully stop all running workers in the pool."""
        async with self._get_lock():
            self._is_running = False
            all_workers = [w for workers in self._workers.values() for w in workers]

        if all_workers:
            await asyncio.gather(*[w.stop(timeout=timeout) for w in all_workers], return_exceptions=True)

        async with self._get_lock():
            for p in self._workers:
                self._workers[p] = []

    def get_allocation(self) -> Dict[Priority, int]:
        """Return the current number of workers assigned per lane."""
        return {p: len(self._workers[p]) for p in Priority}

    def worker_metrics(self) -> WorkerMetrics:
        """Generate real-time WorkerMetrics conforming to the shared metrics contract."""
        crit = len(self._workers[Priority.CRITICAL])
        norm = len(self._workers[Priority.NORMAL])
        be = len(self._workers[Priority.BEST_EFFORT])
        total = crit + norm + be

        all_workers = [w for workers in self._workers.values() for w in workers]
        active = sum(1 for w in all_workers if w.is_active)
        idle = max(0, total - active)
        utilization = (active / total) if total > 0 else 0.0

        return WorkerMetrics(
            critical=crit,
            normal=norm,
            best_effort=be,
            total=total,
            active=active,
            idle=idle,
            utilization=round(utilization, 3),
        )

    def total_events_processed(self) -> int:
        """Total number of events processed across all workers since startup."""
        all_workers = [w for workers in self._workers.values() for w in workers]
        return sum(w.events_processed for w in all_workers)

    def get_workers(self, priority: Optional[Union[Priority, str]] = None) -> List[BaseWorker]:
        """Inspect active workers, optionally filtered by priority lane."""
        if priority is not None:
            p = self._resolve_priority(priority)
            return list(self._workers[p])
        return [w for workers in self._workers.values() for w in workers]

    def __repr__(self) -> str:
        alloc = self.get_allocation()
        return (
            f"<WorkerPool running={self._is_running} "
            f"critical={alloc[Priority.CRITICAL]} "
            f"normal={alloc[Priority.NORMAL]} "
            f"best_effort={alloc[Priority.BEST_EFFORT]}>"
        )


# Default shared worker pool instance
worker_pool = WorkerPool()

__all__ = ["WorkerPool", "worker_pool"]

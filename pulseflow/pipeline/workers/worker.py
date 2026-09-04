"""PulseFlow pipeline: Base Worker abstraction.

Defines the core lifecycle, metrics, and execution contracts for pipeline workers.
Workers consume events from a specific priority lane queue and invoke an EventProcessor.
"""

import abc
import asyncio
from enum import Enum
from typing import Optional
from contracts.priorities import Priority
from pipeline.queues.base_queue import LaneQueue
from pipeline.processing.event_processor import EventProcessor, event_processor


class WorkerState(str, Enum):
    """Lifecycle states of a pipeline worker."""
    IDLE = "IDLE"
    BUSY = "BUSY"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"


class BaseWorker(abc.ABC):
    """Abstract base class for all stream and batch pipeline workers."""

    def __init__(
        self,
        worker_id: str,
        priority: Priority,
        queue: LaneQueue,
        processor: Optional[EventProcessor] = None,
    ) -> None:
        self.worker_id = worker_id
        self.priority = priority
        self.queue = queue
        self.processor = processor or event_processor
        self.state: WorkerState = WorkerState.IDLE

        self._stop_event = asyncio.Event()
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Set = active, Clear = paused
        self._task: Optional[asyncio.Task] = None

        # Worker runtime metrics
        self.events_processed: int = 0
        self.batches_processed: int = 0
        self.errors_count: int = 0
        self.total_latency_ms: float = 0.0

    @property
    def is_active(self) -> bool:
        """True if the worker is currently executing a processing operation."""
        return self.state == WorkerState.BUSY

    @property
    def is_running(self) -> bool:
        """True if the worker loop is started and not stopped."""
        return self.state != WorkerState.STOPPED and not self._stop_event.is_set()

    def start(self) -> None:
        """Start the background consumer task."""
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._pause_event.set()
        self.state = WorkerState.IDLE
        self._task = asyncio.create_task(self._run_loop(), name=f"worker-{self.worker_id}")

    async def stop(self, timeout: float = 3.0) -> None:
        """Gracefully request the worker to stop and await task termination."""
        self._stop_event.set()
        self._pause_event.set()  # Unblock if paused

        if self._task is not None and not self._task.done():
            try:
                await asyncio.wait_for(asyncio.shield(self._task), timeout=timeout)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
                try:
                    await self._task
                except (asyncio.CancelledError, Exception):
                    pass

        self.state = WorkerState.STOPPED

    def pause(self) -> None:
        """Pause event consumption."""
        if self.state != WorkerState.STOPPED:
            self._pause_event.clear()
            self.state = WorkerState.PAUSED

    def resume(self) -> None:
        """Resume event consumption."""
        if self.state == WorkerState.PAUSED:
            self._pause_event.set()
            self.state = WorkerState.IDLE

    @abc.abstractmethod
    async def _run_loop(self) -> None:
        """Core consumer execution loop implemented by subclasses."""
        pass

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} id={self.worker_id} "
            f"priority={self.priority.value} state={self.state.value} "
            f"processed={self.events_processed}>"
        )


__all__ = ["WorkerState", "BaseWorker"]

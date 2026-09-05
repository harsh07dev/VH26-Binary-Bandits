"""PulseFlow pipeline: Batch Worker.

High-throughput worker that micro-batches events for bulk persistence and processing.
Primary processing worker for NORMAL and BEST_EFFORT priority lanes.
"""

import asyncio
import time
from typing import List, Optional
from contracts.priorities import Priority
from contracts.events import Event
from pipeline.queues.base_queue import LaneQueue
from pipeline.processing.event_processor import EventProcessor
from pipeline.workers.worker import BaseWorker, WorkerState
from pipeline.consumer import in_flight_tracker


class BatchWorker(BaseWorker):
    """Worker that buffers events into micro-batches for efficient bulk processing."""

    def __init__(
        self,
        worker_id: str,
        priority: Priority,
        queue: LaneQueue,
        processor: Optional[EventProcessor] = None,
        batch_size: int = 50,
        batch_timeout_ms: float = 100.0,
    ) -> None:
        super().__init__(worker_id=worker_id, priority=priority, queue=queue, processor=processor)
        self.batch_size = max(1, batch_size)
        self.batch_timeout_ms = max(1.0, batch_timeout_ms)

    def set_batch_params(self, batch_size: int, batch_timeout_ms: float) -> None:
        """Dynamically update batch parameters for the next batch collection."""
        self.batch_size = max(1, batch_size)
        self.batch_timeout_ms = max(1.0, batch_timeout_ms)

    async def _run_loop(self) -> None:
        """Continuously collect micro-batches and process them in bulk."""

        while not self._stop_event.is_set():
            await self._pause_event.wait()
            if self._stop_event.is_set():
                break

            current_timeout_sec = self.batch_timeout_ms / 1000.0
            batch: List[Event] = []

            # 1. Wait for the first event in the batch
            try:
                first_event = await asyncio.wait_for(
                    self.queue.get(),
                    timeout=min(0.2, current_timeout_sec),
                )
                batch.append(first_event)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            # 2. Gather subsequent events until current_batch_size is reached or timeout expires
            current_batch_size = self.batch_size
            
            batch_start_time = time.time()
            while len(batch) < current_batch_size and not self._stop_event.is_set():
                elapsed = time.time() - batch_start_time
                remaining = current_timeout_sec - elapsed
                if remaining <= 0:
                    break

                try:
                    next_event = await asyncio.wait_for(
                        self.queue.get(),
                        timeout=remaining,
                    )
                    batch.append(next_event)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    break

            # 3. Process the collected batch
            if batch:
                for event in batch:
                    in_flight_tracker.track(event)

                self.state = WorkerState.BUSY
                try:
                    results = await self.processor.process_batch(batch, mode="BATCH")
                    self.batches_processed += 1
                    self.events_processed += len(batch)
                    self.total_latency_ms += sum(r.latency_ms for r in results)
                    for event in batch:
                        in_flight_tracker.ack(event.event_id)
                except Exception:
                    self.errors_count += 1
                finally:
                    for _ in batch:
                        self.queue.task_done()
                    if not self._stop_event.is_set():
                        self.state = WorkerState.IDLE


__all__ = ["BatchWorker"]

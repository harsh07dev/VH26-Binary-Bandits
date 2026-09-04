"""PulseFlow pipeline: Stream Worker.

Low-latency worker that consumes events immediately one-by-one.
Primary processing worker for the CRITICAL priority lane.
"""

import asyncio
from typing import Optional
from contracts.priorities import Priority
from pipeline.queues.base_queue import LaneQueue
from pipeline.processing.event_processor import EventProcessor
from pipeline.workers.worker import BaseWorker, WorkerState


class StreamWorker(BaseWorker):
    """Worker that streams and processes individual events with minimal latency."""

    def __init__(
        self,
        worker_id: str,
        priority: Priority,
        queue: LaneQueue,
        processor: Optional[EventProcessor] = None,
        poll_interval: float = 0.2,
    ) -> None:
        super().__init__(worker_id=worker_id, priority=priority, queue=queue, processor=processor)
        self.poll_interval = poll_interval

    async def _run_loop(self) -> None:
        """Continuously dequeue and process events one by one."""
        while not self._stop_event.is_set():
            # Respect pause state if active
            await self._pause_event.wait()
            if self._stop_event.is_set():
                break

            try:
                # Wait for next event with a short timeout to allow checking stop_event
                event = await asyncio.wait_for(self.queue.get(), timeout=self.poll_interval)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            self.state = WorkerState.BUSY
            try:
                result = await self.processor.process_single(event, mode="STREAM")
                self.events_processed += 1
                self.total_latency_ms += result.latency_ms
            except Exception:
                self.errors_count += 1
            finally:
                self.queue.task_done()
                if not self._stop_event.is_set():
                    self.state = WorkerState.IDLE


__all__ = ["StreamWorker"]

"""PulseFlow benchmark: Naive FIFO Reference Pipeline.

Simulates the standard, un-prioritized pipeline behavior under surge load:
  - Single un-prioritized FIFO queue with a fixed capacity limit (e.g. 1,000 items).
  - Fixed worker pool treating every event identically without priority awareness.
  - When the queue fills up during a sudden surge (e.g., 20x spike), naive pipelines
    either drop subsequent events (tail-drop) or experience queue overflow, causing
    critical events (orders/payments) to be lost or suffer massive queue wait times.
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional

from contracts.events import Event
from contracts.priorities import Priority


class NaiveFIFOPipeline:
    """A naive reference pipeline with a single FIFO queue and fixed worker pool."""

    def __init__(
        self,
        queue_capacity: int = 1000,
        worker_count: int = 4,
        processing_delay_sec: float = 0.005,  # 5ms simulated processing time per event
    ):
        self.queue_capacity = queue_capacity
        self.worker_count = worker_count
        self.processing_delay_sec = processing_delay_sec

        self.queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=queue_capacity)
        self.workers: list[asyncio.Task] = []
        self._running = False
        self._stop_event = asyncio.Event()

        # Telemetry metrics
        self.total_ingested = 0
        self.total_processed = 0
        self.total_dropped = 0
        self.dropped_by_priority: dict[Priority, int] = {
            Priority.CRITICAL: 0,
            Priority.NORMAL: 0,
            Priority.BEST_EFFORT: 0,
        }
        self.processed_by_priority: dict[Priority, int] = {
            Priority.CRITICAL: 0,
            Priority.NORMAL: 0,
            Priority.BEST_EFFORT: 0,
        }
        self.latencies_ms: dict[Priority, list[float]] = {
            Priority.CRITICAL: [],
            Priority.NORMAL: [],
            Priority.BEST_EFFORT: [],
        }
        self.peak_queue_depth = 0

    async def start(self) -> None:
        """Start the worker pool."""
        self._running = True
        self._stop_event.clear()
        self.workers = [
            asyncio.create_task(self._worker_loop(i))
            for i in range(self.worker_count)
        ]

    async def stop(self) -> None:
        """Stop worker pool and drain pending items."""
        self._running = False
        self._stop_event.set()
        # Cancel or wait for workers
        for worker in self.workers:
            worker.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)

    async def enqueue(self, event: Event) -> bool:
        """Enqueue an incoming event into the naive FIFO queue.
        
        If the queue is full, naive tail-drop occurs, dropping the event regardless
        of whether it is CRITICAL (order/payment) or BEST_EFFORT (click/log).
        """
        priority = event.ensure_priority()
        event.received_at = time.time()
        self.total_ingested += 1

        current_depth = self.queue.qsize()
        if current_depth > self.peak_queue_depth:
            self.peak_queue_depth = current_depth

        try:
            self.queue.put_nowait(event)
            return True
        except asyncio.QueueFull:
            # Queue overflow: Naive FIFO drops whatever arrives next!
            self.total_dropped += 1
            self.dropped_by_priority[priority] += 1
            return False

    async def _worker_loop(self, worker_id: int) -> None:
        """Worker loop continuously popping from FIFO queue."""
        while self._running or not self.queue.empty():
            try:
                event = await asyncio.wait_for(self.queue.get(), timeout=0.1)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                if not self._running and self.queue.empty():
                    break
                continue

            try:
                # Simulate work
                if self.processing_delay_sec > 0:
                    await asyncio.sleep(self.processing_delay_sec)

                finished_at = time.time()
                latency_ms = (finished_at - (event.received_at or event.timestamp)) * 1000.0
                
                priority = event.ensure_priority()
                self.processed_by_priority[priority] += 1
                self.latencies_ms[priority].append(latency_ms)
                self.total_processed += 1
            finally:
                self.queue.task_done()
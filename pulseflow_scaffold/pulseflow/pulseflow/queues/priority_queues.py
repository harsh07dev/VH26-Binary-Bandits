import asyncio
from collections import defaultdict
from typing import Any

class PriorityQueues:
    def __init__(self):
        self._queues = {
            "CRITICAL": asyncio.Queue(),
            "MEDIUM": asyncio.Queue(),
            "LOW": asyncio.Queue(),
        }

    async def put(self, priority: str, event: Any):
        await self._queues[priority].put(event)

    async def get(self, priority: str):
        return await self._queues[priority].get()

    def depth(self, priority: str) -> int:
        return self._queues[priority].qsize()

    def depths(self):
        return {priority: q.qsize() for priority, q in self._queues.items()}

queues = PriorityQueues()

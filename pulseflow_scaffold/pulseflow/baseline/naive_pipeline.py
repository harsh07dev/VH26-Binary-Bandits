import asyncio

class NaivePipeline:
    """Phase 4 baseline: one FIFO queue and identical handling."""

    def __init__(self):
        self.queue = asyncio.Queue()

    async def submit(self, event):
        await self.queue.put(event)

    async def process_one(self):
        event = await self.queue.get()
        return event

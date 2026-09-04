from fastapi import FastAPI
from pulseflow.ingestion.api import router as ingestion_router
from pulseflow.queues.priority_queues import queues

app = FastAPI(title="PulseFlow", version="0.1.0")
app.include_router(ingestion_router)

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "queues": queues.depths(),
    }

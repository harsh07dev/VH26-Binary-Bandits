# PulseFlow

**PulseFlow — Intelligent Adaptive Data Processing Pipeline**

A two-service demonstration system for handling sudden workload surges using business-priority-aware adaptive processing.

## Architecture

- `techpulse/` — Machine 1: workload/event generator
- `pulseflow/` — Machine 2: adaptive processing pipeline
- `baseline/` — naive FIFO baseline
- `benchmark/` — comparison harness
- `tests/` — unit tests

## Initial Phase 1

This scaffold provides a working path:

`TechPulse generator -> HTTP POST /events -> validation -> priority classifier -> priority queues`

Run both services locally first. The same code can later be split across two LAN-connected machines by changing the target host.

## Run

```bash
pip install -r requirements.txt
uvicorn pulseflow.main:app --host 0.0.0.0 --port 8000
```

In another terminal:

```bash
python -m techpulse.main --target http://127.0.0.1:8000/events --rate 60
```

Then open:

`http://127.0.0.1:8000/health`

The `/events` endpoint accepts individual events. The generator continuously sends realistic e-commerce events.

## Priority policy

- CRITICAL: ORDER, PAYMENT
- MEDIUM: CART_ADD, INVENTORY_UPDATE
- LOW: PAGE_VIEW, CLICK, LOG

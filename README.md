<div align="center">

#  PulseFlow

**Adaptive Priority-Aware Event Processing Pipeline**

*Observe system pressure. Classify workload importance. Protect what matters.*

[![Python](https://img.shields.io/badge/Python-3.11-3776ab?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-Latest-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-0ea5e9?style=flat-square&logo=react&logoColor=white)](https://react.dev)
[![AsyncIO](https://img.shields.io/badge/AsyncIO-Concurrent-6366f1?style=flat-square)](https://docs.python.org/3/library/asyncio.html)
[![SQLite](https://img.shields.io/badge/Storage-SQLite-003b57?style=flat-square&logo=sqlite&logoColor=white)](https://sqlite.org)



</div>

---

## Overview

PulseFlow is an intelligent event-processing pipeline built for unpredictable traffic. Instead of treating every event identically, it classifies workloads by business priority and continuously measures system pressure — then adapts: reallocating workers, switching processing strategies, and shedding low-value work so critical events always get through.

A static pipeline under load buries payments in the same queue as page views. PulseFlow never lets that happen.

---

## The Problem with Static Pipelines

```
Incoming Events → Fixed Queues → Fixed Workers → Fixed Processing → Database
```

When traffic spikes, everything degrades equally. Queues grow. Latency climbs. Orders and payments compete with click events for the same workers, and there is no mechanism to protect what matters most.

PulseFlow introduces a layer of adaptive intelligence between ingestion and processing.

---

## Architecture

```
                 ┌─────────────────────┐
                 │      TECH PULSE     │
                 │   Traffic Generator │
                 └──────────┬──────────┘
                            │ HTTP POST /events/batch
                            ▼
                 ┌─────────────────────┐
                 │     INGESTION       │
                 │  Validate · Stamp   │
                 └──────────┬──────────┘
                            ▼
                 ┌─────────────────────┐
                 │   CLASSIFICATION    │
                 └──────────┬──────────┘
                            │
             ┌──────────────┼──────────────┐
             ▼              ▼              ▼
        CRITICAL          NORMAL       BEST-EFFORT
          QUEUE            QUEUE           QUEUE
             └──────────────┼──────────────┘
                            ▼
                 ┌─────────────────────┐
                 │  ADAPTIVE GOVERNOR  │
                 │                     │
                 │  Pressure Score     │
                 │  Policy Engine      │
                 │  Decision Engine    │
                 └──────────┬──────────┘
                            ▼
                 ┌─────────────────────┐
                 │    WORKER POOL      │
                 │  Stream · Batch     │
                 └──────────┬──────────┘
                            ▼
                       SQLite DB
                            ▼
                 ┌─────────────────────┐
                 │  PULSEFLOW DASHBOARD│
                 │  React Observability│
                 └─────────────────────┘
```

---

## Priority Classification

Every event is classified into one of three tiers at ingestion time.

| Tier | Example Events | Guarantee |
|---|---|---|
| 🔴 **Critical** | `PAYMENT`, `ORDER` | Always stream-processed. Never shed. Workers scale up to protect this tier under pressure. |
| 🟡 **Normal** | `CART`, `INVENTORY` | Stream or micro-batched. Deferred under extreme pressure. |
| 🟢 **Best-Effort** | `CLICK`, `PAGE_VIEW`, `LOG` | Stream normally. Sampled or shed when capacity is constrained. |

```
              Incoming Event
                    │
                    ▼
              CLASSIFIER
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
     CRITICAL     NORMAL    BEST-EFFORT
     PAYMENT       CART       CLICK
     ORDER       INVENTORY  PAGE_VIEW
```

---

## Adaptive Governor

The governor continuously measures four signals and computes a normalized pressure score from 0 to 1.

| Signal | Weight |
|---|---|
| Queue depth | 40% |
| Worker utilization | 30% |
| Ingress / processing rate ratio | 15% |
| Processing latency | 15% |

The score maps to one of three pressure states, each triggering a distinct response.

### 🟢 Normal

System is operating comfortably. All tiers process at full capacity.

| Tier | Strategy | Workers |
|---|---|---|
| Critical | Stream | 2 |
| Normal | Stream / Batch | 4 |
| Best-Effort | Stream | 2 |

### 🟡 High

Traffic increasing. Resources shift toward higher-priority work.

| Tier | Strategy | Workers |
|---|---|---|
| Critical | Stream | 3 |
| Normal | Micro-batch | 4 |
| Best-Effort | Sample | 1 |

### 🔴 Extreme

System under severe load. Best-effort workers are reassigned to protect critical throughput.

| Tier | Strategy | Workers |
|---|---|---|
| Critical | Stream | 4 |
| Normal | Defer | 4 |
| Best-Effort | Sample / Shed | 0 |

---

## Processing Strategies

| Strategy | Description |
|---|---|
| **Stream** | Process immediately as events arrive. |
| **Micro-batch** | Collect a short window of events and process together, reducing write overhead. |
| **Sample** | Retain a statistically representative fraction — not every analytics event needs storage under load. |
| **Defer** | Hold lower-priority work temporarily while higher-priority queues clear. |
| **Shed** | Drop non-essential events when pressure is extreme. Safe for page views; never used for payments. |

---

## Adaptive Response Flow

```
Traffic spike: 100 → 4,000 events/sec

  PulseFlow observes:
    Queue depth ↑
    Worker utilization ↑
    Processing latency ↑
    Ingress rate > processing rate

  Pressure state: NORMAL → HIGH → EXTREME

  System responds:
    CRITICAL    → Stream + reallocated workers    (fully protected)
    NORMAL      → Micro-batch → Defer             (optimized)
    BEST-EFFORT → Sample → Shed                   (sacrificed safely)

Spike subsides: 4,000 → 100 events/sec

  Queues drain.
  Pressure falls.
  Workers return to default allocation.
```

---

## Tech Pulse — Load Generator

Tech Pulse simulates realistic concurrent workloads using multiple parallel producers, enabling sustained high event rates that a single sequential sender cannot produce.

```
Producer 1 ──┐
Producer 2 ──┤
Producer 3 ──┼──▶ PulseFlow :8000
Producer 4 ──┘
```

Supports configurable event mixes, concurrency levels, and burst patterns for stress-testing the adaptive pipeline end-to-end.

---

## Observability Dashboard

A React dashboard backed by actual backend telemetry — all values are measured, none are derived or simulated.

**System Overview**
- Live ingress rate via sliding-window rate tracker (decays correctly when traffic stops)
- Real-time pressure score and governor state
- Queue depth per tier

**Worker Allocation**
- Per-tier worker counts against total pool
- Overall utilization

**Queue Health**
- Per-tier processing latency — Critical / Normal / Best-Effort

**Backpressure**
- Shed, deferred, and sampled event counts

**Live Event Stream**
- Timestamp · Event type · Priority tier · Routing decision

**Event Mix**
- Distribution computed from recent observed events — not hardcoded

**Connection Status**
- 🟢 Live — telemetry requests succeeding
- 🔴 Disconnected — backend unreachable, prevents silently displaying stale data

---

## Two-Machine Setup

PulseFlow supports running the traffic generator on a separate machine from the processing backend.

```
          SAME Wi-Fi / LAN
──────────────────────────────────────

  MACHINE 1               MACHINE 2
 ┌────────────┐          ┌──────────────────┐
 │ TECH PULSE │          │  PulseFlow API   │
 │            │─ HTTP ──▶│  :8000           │
 │ Traffic Gen│          │                  │
 └────────────┘          │  Dashboard :5174 │
                         └──────────────────┘
```

The backend binds to `0.0.0.0:8000` and is reachable from any host on the LAN.

---

## API Reference

### Ingest events

```http
POST /events/batch
Content-Type: application/json

{
  "events": [
    { "type": "PAYMENT", "track_id": "...", "payload": {} },
    { "type": "CLICK",   "track_id": "...", "payload": {} }
  ]
}
```

### Fetch live telemetry

```http
GET /metrics/adaptive
```

**Response includes:**

```json
{
  "queue_depth":        { "critical": 0, "normal": 12, "best_effort": 340 },
  "ingress_rate":       428.3,
  "processing_latency": { "critical": 2.1, "normal": 18.4, "best_effort": 94.7 },
  "throughput":         391.0,
  "pressure_state":     "HIGH",
  "pressure_score":     0.71,
  "worker_allocation":  { "critical": 3, "normal": 4, "best_effort": 1 },
  "backpressure":       { "shed": 0, "deferred": 89, "sampled": 612 },
  "recent_events":      []
}
```

---

## Baseline Comparison

The repo includes a fixed-strategy baseline pipeline. Run both under identical traffic to measure the difference adaptive processing makes.

```
              Same Traffic
                   │
       ┌───────────┴───────────┐
       ▼                       ▼
  BASELINE                 PULSEFLOW
  Fixed strategy           Adaptive strategy
  Fixed workers            Dynamic reallocation
  No priority              Three-tier classification
  No backpressure          Sample / defer / shed
       └───────────┬───────────┘
                   ▼
               BENCHMARK
```

**Benchmark metrics:** throughput · avg latency · P95 latency · critical event latency · queue depth · worker utilization · dropped events · critical events dropped

---

## Tech Stack

| Layer | Technology |
|---|---|
| Processing engine | Python + AsyncIO |
| API | FastAPI |
| Dashboard | React + Vite |
| Charting | Recharts |
| Icons | Lucide React |
| Storage | SQLite |
| Testing | Pytest |

---

## Project Structure

```
VH26-Binary-Bandits/
│
├── pulseflow/
│   ├── techpulse/              # Concurrent traffic generator
│   │   ├── frontend/
│   │   ├── generator/
│   │   ├── config.py
│   │   └── main.py
│   │
│   ├── pipeline/               # Core ingestion and processing
│   │   ├── main.py
│   │   ├── ingestion/
│   │   ├── queue/
│   │   ├── workers/
│   │   └── storage/
│   │
│   ├── adaptive/               # Governor, policy, and allocation
│   │   ├── pressure_calculator.py
│   │   ├── pressure_config.py
│   │   ├── policy_engine.py
│   │   ├── decision_engine.py
│   │   ├── worker_allocator.py
│   │   └── sampler.py
│   │
│   ├── observability/
│   │   └── dashboard/          # React telemetry dashboard
│   │
│   ├── baseline/               # Fixed-strategy comparison pipeline
│   └── benchmark/              # Head-to-head benchmark runner
│
└── tests/
    ├── adaptive/               # 35 tests
    ├── pipeline/               # 40 tests
    └── techpulse/              # 155 tests
```

---

## Running the Tests

```bash
# All tests
pytest

# By module
pytest tests/pipeline/
pytest tests/adaptive/
pytest tests/techpulse/
```

```
Pipeline      40 passed
Adaptive      35 passed
TechPulse    155 passed
─────────────────────────
Total        230 passed
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- pnpm or npm

### Backend

```bash
cd pulseflow/pipeline
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Dashboard

```bash
cd pulseflow/observability/dashboard
pnpm install
pnpm dev
# http://localhost:5174
```

### Tech Pulse

```bash
cd pulseflow/techpulse
pip install -r requirements.txt
python main.py --target http://<backend-ip>:8000 --producers 4
```

---

## Mental Model

```
             PULSEFLOW
                 │
        ┌────────┴────────┐
        │                 │
     OBSERVE            ADAPT
        │                 │
 Queue / Rate /       Workers /
 Latency / Load       Policies
        │                 │
        └────────┬────────┘
                 ▼
             PRIORITY
                 ▼
       ┌─────────┼─────────┐
       ▼         ▼         ▼
    CRITICAL   NORMAL  BEST-EFFORT
       ▼         ▼         ▼
     STREAM    BATCH   SAMPLE/SHED
                 ▼
          PROCESS → MEASURE → ADAPT
```

When capacity is constrained, PulseFlow does not treat all events equally. It treats them correctly.

---


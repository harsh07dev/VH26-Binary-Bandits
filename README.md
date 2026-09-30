<div align="center">

# ⚡ PulseFlow

**Adaptive Priority-Aware Event Processing Pipeline & Digital Oscilloscope Telemetry**

*Observe system pressure. Classify workload importance. Protect what matters.*

[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.14-3776ab?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-Production%20Ready-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-0ea5e9?style=for-the-badge&logo=react&logoColor=white)](https://react.dev)
[![Vite](https://img.shields.io/badge/Vite-Build%20Tool-646CFF?style=for-the-badge&logo=vite&logoColor=white)](https://vitejs.dev)
[![AsyncIO](https://img.shields.io/badge/AsyncIO-Concurrent%20Engine-6366f1?style=for-the-badge)](https://docs.python.org/3/library/asyncio.html)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

<br/>

[Overview](#overview) •
[Why PulseFlow](#the-problem-with-static-pipelines) •
[Architecture](#architecture) •
[Key Innovations](#key-architectural-innovations) •
[Benchmarking](#head-to-head-benchmark-results) •
[Digital Oscilloscope](#digital-oscilloscope-observability) •
[Quickstart](#getting-started) •
[API Reference](#api-reference)

---

</div>

## Overview

**PulseFlow** is a distributed, adaptive event-processing pipeline engineered for volatile, unpredictable traffic surges. 

Traditional static message pipelines treat every incoming payload identically — queuing payment transactions, order submissions, and page clicks into the exact same FIFO buffers. Under severe load, queues bloat, latency explodes, and critical financial transactions are silently dropped or timeout while low-value analytics hog worker bandwidth.

PulseFlow solves this fundamental bottleneck:
1. **Tiered Priority Classification**: Workloads are classified at ingestion into Critical (Tier 1), Normal (Tier 2), and Best-Effort (Tier 3).
2. **Continuous System Pressure Observation**: An autonomous Governor evaluates multi-signal metrics ($\text{Queue Depth}$, $\text{Worker Load}$, $\text{Ingress/Drain Ratio}$, $\text{Processing Latency}$) in real time.
3. **Adaptive Dynamic Execution**: Automatically scales dedicated worker allocations, shifts processing strategies (streaming $\to$ vectorized micro-batching $\to$ deferral $\to$ statistical sampling $\to$ load shedding), and enforces a **Zero-Loss Critical Invariant** for mission-critical operations.

```
                  ┌────────────────────────────────────────┐
                  │          UNPREDICTABLE SPIKE           │
                  │   100 ev/s  ──▶  4,000+ ev/s (20x)     │
                  └───────────────────┬────────────────────┘
                                      │
            ┌─────────────────────────┴─────────────────────────┐
            ▼                                                   ▼
┌───────────────────────┐                           ┌───────────────────────┐
│   STATIC FIFO QUEUE   │                           │       PULSEFLOW       │
├───────────────────────┤                           ├───────────────────────┤
│ ❌ All events treated │                           │ ✅ Tier 1 Protected   │
│    identically        │                           │    (0 payments lost)  │
│ ❌ Tail-drops critical│                           │ ✅ Dynamic Re-balance │
│    transactions       │                           │    (3-lane workers)   │
│ ❌ Unbounded latency  │                           │ ✅ Vectorized Micro-  │
│    (1000ms+ backlog)  │                           │    Batching (dq/dt)   │
│ ❌ Total buffer bloat │                           │ ✅ Statistical Sample │
│    & thread crash     │                           │    & Safe Shedding    │
└───────────────────────┘                           └───────────────────────┘
```

---

## Architecture

PulseFlow is designed with a high-performance **Two-Machine Distributed Architecture** connected via high-throughput HTTP/2 batch ingestion:

```
 MACHINE 1: TECHPULSE WORKLOAD ENGINE             MACHINE 2: PULSEFLOW ADAPTIVE PIPELINE
 (Port 5173 / Port 8001)                          (Port 5174 / Port 8000)
 ┌────────────────────────────────────┐           ┌────────────────────────────────────┐
 │  Synthetic Traffic & Surge Gen     │           │  FastAPI Ingestion & Validation    │
 │  • Multiplier Deck (+1x to +20x)   │           │  • Nanosecond timestamping         │
 │  • Dynamic Event Mix Sliders       │─ HTTP ───▶│  • Schema audit & classification   │
 │  • Continuous Workload Generator   │  Batch    └─────────────────┬──────────────────┘
 └────────────────────────────────────┘                             │
                                                                    ▼
                                                  ┌────────────────────────────────────┐
                                                  │  Priority Partitioning Queues      │
                                                  │  • Tier 1: CRITICAL (Payments)     │
                                                  │  • Tier 2: NORMAL   (Carts/Orders) │
                                                  │  • Tier 3: BEST-EFFORT (Clicks)    │
                                                  └─────────────────┬──────────────────┘
                                                                    │
                                                                    ▼
                                                  ┌────────────────────────────────────┐
                                                  │  Adaptive Backpressure Governor    │
                                                  │  • Multi-signal pressure score     │
                                                  │  • Dynamic worker reallocation     │
                                                  │  • Adaptive batch sizer (dq/dt)    │
                                                  └─────────────────┬──────────────────┘
                                                                    │
                                                                    ▼
                                                  ┌────────────────────────────────────┐
                                                  │  Worker Pool & Fault-Tolerant Sink │
                                                  │  • In-flight timeout tracker       │
                                                  │  • Stream / Micro-batch / Sample   │
                                                  │  • SQLite WAL / Persistent Storage │
                                                  └─────────────────┬──────────────────┘
                                                                    │
                                                                    ▼
                                                  ┌────────────────────────────────────┐
                                                  │  Digital Oscilloscope Dashboard    │
                                                  │  • Hardware-grade DSO waveform     │
                                                  │  • Naive vs. PulseFlow comparison  │
                                                  │  • Live SLA budgets & HUD telemetry│
                                                  └────────────────────────────────────┘
```

---

## Key Architectural Innovations

### 1. Zero-Loss Critical Invariant (Tier 1 Protection)
Critical transactions (`PAYMENT`, `ORDER`) are guaranteed:
- **Zero Shedding**: Under no circumstance is a Tier 1 event discarded, sampled, or dropped.
- **Dedicated Worker Reservation**: When pressure transitions to `EXTREME`, workers are immediately re-assigned from Best-Effort lanes to guarantee minimum latency for critical items.
- **Dedicated Execution Lane**: Critical traffic bypasses batch delays and processes via immediate real-time stream execution.

### 2. Multi-Signal Adaptive Governor
The governor computes a composite normalized pressure index $P \in [0, 1]$ updated continuously:

$$P = 0.40 \cdot \bar{Q}_{\text{depth}} + 0.30 \cdot W_{\text{util}} + 0.15 \cdot \left(\frac{R_{\text{in}}}{R_{\text{proc}}}\right) + 0.15 \cdot L_{\text{norm}}$$

| Pressure State | Trigger Score | Tier 1 (Critical) | Tier 2 (Normal) | Tier 3 (Best-Effort) | Worker Allocation |
|:---:|:---:|:---|:---|:---|:---:|
| 🟢 **NORMAL** | $P < 0.40$ | Stream Process | Stream Process | Stream Process | $W_1=2, W_2=4, W_3=2$ |
| 🟡 **HIGH** | $0.40 \le P < 0.75$ | Stream Process | Adaptive Micro-Batch | Statistical Sample (20%-50%) | $W_1=3, W_2=4, W_3=1$ |
| 🔴 **EXTREME** | $P \ge 0.75$ | Stream (Priority) | Defer / Deep Buffer | Safe Load Shedding | $W_1=4, W_2=4, W_3=0$ |

### 3. Dynamic Micro-Batching & Adaptive Batch Sizer ($dq/dt$)
Under rising pressure, Normal traffic dynamically transitions from single-event streaming to vectorized batch execution. The adaptive batch sizer monitors queue rate-of-change ($dq/dt$):
- Accelerates batch sizes up to configured maximum limits to amortize disk I/O and transaction overhead.
- Automatically contracts batch timeouts when the queue stabilizes to maintain responsive latency.

### 4. Anti-Starvation Lazy Priority Aging
To prevent low-priority events from being starved indefinitely behind persistent high-priority streams, PulseFlow employs **Lazy Priority Aging**:
- Events in lower-tier queues accumulate aging credits proportional to queue residence time.
- Aged Best-Effort events are transparently promoted to normal dispatch lanes, establishing a hard upper bound ($P_{100}$) on worst-case tail wait times.

### 5. In-Flight Tracking Buffer & Crash Fault Recovery
Every consumer worker registers events into an atomic in-flight tracker prior to database writes. If a worker thread terminates unexpectedly mid-surge:
- An active timeout watchdog intercepts un-ACKed items.
- Re-queues un-ACKed transactions directly into the CRITICAL lane with idempotency guarantees, ensuring **100% crash recovery with zero lost state**.

---

## Head-to-Head Benchmark Results

PulseFlow was evaluated against a standard Naive FIFO pipeline under an extreme **100,000-event Flash Sale surge**:

| Performance Metric | Naive FIFO Pipeline | PulseFlow Pipeline | PulseFlow Advantage |
|:---|:---:|:---:|:---|
| **Total Ingested Events** | 100,000 | 100,000 | Identical load test |
| **Critical Events Lost** | `8,496` ❌ | **`0`** ✅ | **Zero Silent Drops (Guaranteed)** |
| **Critical Delivery Rate** | 15.6% | **100.0%** | **100% Transaction Integrity** |
| **Critical Latency (Avg)** | 709.91 ms | **142.02 ms** | **-80.0% Latency Reduction** |
| **Critical Latency (P95)** | 968.03 ms | **212.21 ms** | **-78.1% Predictable SLA** |
| **Critical Latency (P99)** | 998.85 ms | **252.63 ms** | **-74.7% Tail Latency Protection** |
| **Peak Queue Depth** | 15,000 (Saturated) | 1,000 (Managed) | **No Buffer Bloat** |
| **Best-Effort Shedding** | 51,062 (Uncontrolled) | 59,119 (Controlled) | Graceful Degrade of Clicks/Logs |
| **Normal Micro-Batched** | 0 (None) | 1,000 | Vectorized I/O Efficiency |
| **In-Flight Crash Recovery** | 0% (Data Lost) | **100% In-Flight Re-queued** | **Zero Lost In-Flight State** |

> *Full benchmark artifact and history available in [pulseflow/benchmark/results/README.md](pulseflow/benchmark/results/README.md).*

---

## Digital Oscilloscope Observability

The **PulseFlow Observability Dashboard** (`http://localhost:5174`) provides an authentic, hardware-grade Digital Storage Oscilloscope (DSO) canvas built for operational engineering:

- **Sub-Pixel Grid & Laser Phosphor Sweep**: True cathode-ray oscilloscope appearance with bounded radar scanline sweeps.
- **SVG Neon Beam Laser Filters**: Hardware laser glow rendering with Gaussian blur stroke synthesis.
- **Live 5-Metric Telemetry HUD**:
  - `TOTAL BACKLOG` with synchronous clear indicators.
  - `TIER 1 (CRITICAL) QUEUE` with Zero-Loss Invariant monitoring.
  - `NET DRAIN VELOCITY` calculating instantaneous $R_{\text{proc}} - R_{\text{in}}$.
  - `ESTIMATED CLEAR TIME` providing real-time $Q_{\text{depth}} / \text{DrainRate}$ drain projections.
  - `AVERAGE LATENCY` real-time SLA tracking meter with dynamic `< 20ms` target validation.
- **Buffer Bloat Comparison**: Real-time side-by-side comparison tracking the difference between PulseFlow's managed queue depth and Naive FIFO unbounded buffer bloat.
- **Interactive Freeze & Scrubbing**: Freeze the live oscilloscope stream to inspect individual transient surge peaks without losing live telemetry.

---

## TechPulse — Workload & Surge Generator

The **TechPulse Workload Generator** (`http://localhost:5173` / `http://localhost:8001`) acts as Machine 1 in the distributed architecture:

- **Multiplier Surge Deck**: Instantly inject `+1x`, `+5x`, `+10x`, or `+20x` peak traffic spikes.
- **Live Event Mix Tuning**: Interactively re-balance the distribution of incoming events:
  - Critical Traffic: `PAYMENT`, `ORDER`
  - Normal Traffic: `CART_ADD`, `INVENTORY_UPDATE`
  - Best-Effort Traffic: `CLICK`, `PAGE_VIEW`, `LOG`
- **Dynamic Stress Projection Engine**: Visualizes expected system pressure, drain capacity, and worker load before triggering surges.
- **Inter-Machine Pipeline Transmission Bridge**: Animated visual bridge monitoring HTTP 200 delivery confirmations, round-trip latency, and aggregate transmission volume.

---

## Project Structure

```
VH26-Binary-Bandits/
├── pulseflow/
│   ├── pipeline/               # Core Ingestion & Execution Pipeline (Machine 2)
│   │   ├── main.py             # FastAPI entrypoint, routes, & telemetry collector
│   │   ├── config.py           # Pipeline configuration & environment bindings
│   │   ├── ingestion/          # Schema audit, validation, & priority tagging
│   │   ├── queues/             # Priority queues (Critical, Normal, Best-Effort)
│   │   ├── workers/            # Worker pool, dynamic reallocation, & fault tolerance
│   │   ├── processing/         # Stream execution, telemetry tracker, & event processor
│   │   └── storage/            # SQLite WAL persistent repository
│   │
│   ├── adaptive/               # Autonomous Governor Engine
│   │   ├── pressure_calculator.py  # 4-signal composite pressure score calculator
│   │   ├── policy_engine.py        # Strategy matrix & state transitions
│   │   ├── decision_engine.py      # Action decision synthesizer (Stream/Batch/Shed)
│   │   ├── worker_allocator.py     # Dynamic multi-lane thread allocation
│   │   ├── batch_sizer.py          # Dynamic dq/dt batch size optimizer
│   │   └── sampler.py              # Statistical downsampling algorithms
│   │
│   ├── techpulse/              # Traffic Generator & Surge Engine (Machine 1)
│   │   ├── main.py             # Control API server (:8001) & producer loop
│   │   ├── config.py           # Workload rates, event mix, & network settings
│   │   ├── generator/          # Traffic generator, event factory, & rate profiles
│   │   ├── client/             # Async HTTP/2 connection pool & batch client
│   │   └── frontend/           # TechPulse React UI (:5173)
│   │
│   ├── observability/
│   │   └── dashboard/          # React Observability Dashboard (:5174)
│   │       ├── src/pages/      # ObservabilityPage with Digital Oscilloscope
│   │       ├── src/api/        # Telemetry service & WebSocket subscribers
│   │       └── src/index.css   # Neon laser tokens & oscilloscope styling
│   │
│   ├── baseline/               # Static FIFO comparison pipeline
│   ├── benchmark/              # Automated comparison suite & test runner
│   └── tests/                  # Full pytest regression test suite (250+ tests)
│       ├── pipeline/
│       ├── adaptive/
│       └── techpulse/
│
├── WALKTHROUGH.md              # Detailed engineering evolution & verification logs
└── README.md                   # Authoritative system documentation
```

---

## Getting Started

### Prerequisites
- **Python 3.11+**
- **Node.js 18+** & **npm**

---

### Step 1: Install Dependencies

```bash
# Clone the repository
git clone https://github.com/harsh07dev/VH26-Binary-Bandits.git
cd VH26-Binary-Bandits

# Install Python requirements
pip install -r pulseflow/pipeline/requirements.txt
pip install -r pulseflow/techpulse/requirements.txt

# Install Frontend dependencies
cd pulseflow/observability/dashboard && npm install && cd ../../..
cd pulseflow/techpulse/frontend && npm install && cd ../../..
```

---

### Step 2: Start PulseFlow (Machine 2)

Terminal 1 — Pipeline Backend:
```bash
# Set PYTHONPATH and start FastAPI ingestion backend
$env:PYTHONPATH="pulseflow"
python -m uvicorn pipeline.main:app --host 0.0.0.0 --port 8000
```

Terminal 2 — Observability Dashboard:
```bash
cd pulseflow/observability/dashboard
npm run dev
# Observability Dashboard active at http://localhost:5174
```

---

### Step 3: Start TechPulse (Machine 1)

Terminal 3 — TechPulse Generator Backend:
```bash
$env:PYTHONPATH="pulseflow"
python -m techpulse.main
# TechPulse Control API active at http://localhost:8001
```

Terminal 4 — TechPulse Frontend:
```bash
cd pulseflow/techpulse/frontend
npm run dev
# TechPulse Spiker UI active at http://localhost:5173
```

---

## Two-Machine Distributed Setup

PulseFlow is designed to run seamlessly across two physical machines over local Wi-Fi / Ethernet:

```
 MACHINE 1 (Generator)                   MACHINE 2 (Pipeline & Dashboard)
 IP: 192.168.1.150                       IP: 192.168.1.200
 ┌────────────────────────┐              ┌────────────────────────┐
 │ TechPulse API   :8001  │              │ PulseFlow API   :8000  │
 │ TechPulse UI    :5173  │──── LAN ────▶│ Observability   :5174  │
 └────────────────────────┘              └────────────────────────┘
```

1. On **Machine 2**, start the pipeline on `0.0.0.0:8000`. Note Machine 2's LAN IP (e.g., `192.168.1.200`).
2. On **Machine 1**, set the target variable and launch TechPulse:
   ```bash
   $env:TECHPULSE_TARGET="http://192.168.1.200:8000"
   python -m techpulse.main
   ```
3. Open `http://localhost:5173` on Machine 1 and `http://192.168.1.200:5174` on Machine 2.

---

## API Reference

### 1. Ingest Event Batch
`POST /events/batch`
```json
{
  "events": [
    {
      "event_id": "evt_8f3a9b1c",
      "event_type": "PAYMENT",
      "timestamp": 1788600000.123,
      "payload": { "account_id": "act_991", "amount": 249.99, "currency": "USD" }
    },
    {
      "event_id": "evt_4b2c1a0e",
      "event_type": "CLICK",
      "timestamp": 1788600000.124,
      "payload": { "element": "btn_add_to_cart", "page": "/items/481" }
    }
  ]
}
```
**Response:** `HTTP 202 Accepted`

---

### 2. Fetch Live Telemetry
`GET /metrics/adaptive`
```json
{
  "metrics": {
    "queueSize": 24,
    "latency": 16.8,
    "workerLoad": 62.5,
    "ingress": 450.0,
    "throughput": 448.0,
    "pressureScore": 0.38,
    "pressureState": "NORMAL"
  },
  "infraMetrics": {
    "queueT1": 0, "latT1": 2.1,
    "queueT2": 8, "latT2": 14.3,
    "queueT3": 16, "latT3": 38.0,
    "w1": 2, "w2": 4, "w3": 2,
    "totalWorkers": 8
  },
  "shedStats": {
    "shed": 0,
    "deferred": 0,
    "sampled": 0,
    "sampled_kept": 0,
    "sampled_dropped": 0,
    "batched": 0,
    "streamed": 1420,
    "critical_protected": 380
  }
}
```

---

### 3. Trigger Custom Spike
`POST /control/spike` (TechPulse API :8001)
```json
{
  "profile": "surge",
  "intensity": 10.0,
  "duration_seconds": 15.0,
  "mix": {
    "CRITICAL": 0.20,
    "NORMAL": 0.40,
    "BEST_EFFORT": 0.40
  }
}
```

---

## Running Automated Tests

Run the full pytest suite across pipeline, adaptive governor, and TechPulse modules:

```bash
# Run all unit and integration tests
$env:PYTHONPATH="pulseflow"
pytest tests/ -v

# Run by subsystem
pytest tests/pipeline/     # Priority queues, workers, storage, fault tolerance
pytest tests/adaptive/     # Pressure score, policies, decision engine, aging
pytest tests/techpulse/    # Traffic generator, profiles, client pool, control API
```

---

## Engineering Verification & Walkthrough

For full historical logs, oscilloscope engineering notes, visual design tokens, and benchmark walkthroughs:
- **[WALKTHROUGH.md](WALKTHROUGH.md)** — Comprehensive architecture evolution and live verification audit.
- **[pulseflow/benchmark/results/README.md](pulseflow/benchmark/results/README.md)** — Head-to-head empirical benchmark dataset.

---

<div align="center">
<b>PulseFlow</b> — Built with precision for unpredictable stream processing.
</div>

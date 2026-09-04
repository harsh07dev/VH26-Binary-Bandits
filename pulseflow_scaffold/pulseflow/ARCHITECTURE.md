# PulseFlow Architecture

## Two-machine deployment

```text
MACHINE 1                                  MACHINE 2
TechPulse                                  PulseFlow
Workload Generator                         Intelligent Pipeline

Users / Flash Sale                         FastAPI Ingestion
       |                                         |
       v                                         v
Event Generator --------------------------> Priority Classifier
             HTTP / LAN                         |
                                                 v
                                      +----------+----------+
                                      |          |          |
                                  CRITICAL    MEDIUM       LOW
                                    Queue       Queue      Queue
                                      |          |          |
                                      +----------+----------+
                                                 |
                                                 v
                                         Decision Engine
                                                 |
                                  +--------------+--------------+
                                  |              |              |
                               STREAM          BATCH          DEFER
                                  |              |              |
                                  +--------------+--------------+
                                                 |
                                                 v
                                               Workers
                                                 |
                                                 v
                                              SQLite
                                                 |
                                                 v
                                           Observability
                                                 |
                                                 v
                                            Dashboard
                                                 |
                                                 +----> feedback
```

## Adaptive policy

The pressure score combines queue pressure, incoming/processing rate ratio, worker utilization and latency relative to SLA.

```text
pressure =
    w1 * queue_pressure
  + w2 * rate_pressure
  + w3 * worker_utilization
  + w4 * latency_pressure
```

Initial policy:

| Pressure | Critical | Medium | Low |
|---|---|---|---|
| < 0.4 | STREAM | STREAM | STREAM |
| 0.4–0.7 | STREAM | BATCH | BATCH |
| 0.7–0.9 | STREAM | BATCH | DEFER |
| > 0.9 | STREAM | DEFER | SHED |

Critical events are never selected for shedding.

## Traffic profiles

- Normal: approximately 1×
- Surge: approximately 20×

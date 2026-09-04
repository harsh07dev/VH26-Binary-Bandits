# PulseFlow

Intelligent Adaptive Data Processing Pipeline.

## Repository ownership
- `techpulse/` — Machine 1 workload generator (Harsh)
- `pipeline/` — Machine 2 processing infrastructure (Aradhya)
- `adaptive/` — adaptive scheduler/intelligence (Shrikar)
- `observability/` + `benchmark/` — dashboard, metrics and benchmarking (Mayur)
- `contracts/` — shared, frozen interfaces
- `baseline/` — naive reference pipeline

## Runtime flow
TechPulse → HTTP → Ingestion → Classification → 3 logical queues → Adaptive Scheduler → Dynamic worker allocation → Processing → Storage → Observability.

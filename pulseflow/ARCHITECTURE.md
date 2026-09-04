# PulseFlow Architecture

Two-machine architecture with three logical processing lanes.

Machine 1: TechPulse generates normal and 20× surge traffic.

Machine 2: PulseFlow receives events, classifies them as CRITICAL/NORMAL/BEST-EFFORT, routes them into separate logical queues, and uses an adaptive scheduler to adjust processing mode and worker allocation.

Under pressure:
- CRITICAL: protected, streaming, dedicated capacity
- NORMAL: micro-batched and/or deferred
- BEST-EFFORT: sampled or shed; its workers may be paused/reassigned

The dashboard observes traffic, pressure, queue depth, worker allocation, latency, decisions and critical-event loss.

# Correctness Score Model

Faultline++ exposes a correctness score so operators can reason about system health beyond raw throughput.

## Inputs
- duplicate commits
- stale write rejections
- jobs stuck running
- reconciled jobs
- lease reclaim volume

## Interpretation
- 100: clean protected execution path
- 90-99: safe, but review near-miss signals
- <90: review required before calling the workload production-safe
- any duplicate commit: correctness violation

## Why this exists
Most queue dashboards tell you throughput.
Faultline++ should tell you whether correctness is holding under failure.

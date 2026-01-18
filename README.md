# Faultline — Distributed Job System

## What it is
A local-first, production-minded distributed job system that provides durable execution with retries, leasing, idempotency, and crash recovery.

## Why it exists
Most job systems work when everything is healthy. Faultline is designed to survive when things break:
- workers crash
- jobs are delivered twice
- databases go temporarily unavailable

The goal is to make failure modes explicit, observable, and recoverable.

## Architecture
![architecture](docs/architecture.png)

## Reliability guarantees
- **At-least-once execution** with idempotency
- **Leasing** to prevent stuck or orphaned jobs
- **Retries with backoff** and bounded attempts
- **Crash recovery** via lease expiration

## Failure modes & recovery drills
Faultline includes documented failure drills that demonstrate how the system behaves under real faults:
- Worker crash mid-job
- Duplicate job submission
- Database outage during execution

Each drill includes expected outcomes and metrics to observe.

## Observability
Faultline exposes Prometheus metrics from both the API and worker:
- Job lifecycle counters
- Execution duration
- Retry and lease expiry events

Metrics are designed to make failures visible, not hidden.

## Local quickstart
```bash
make up

## Failure drills (reproducible)

Faultline ships with operational drills that validate correctness under real failure:

- **Worker crash mid-job:** leased jobs are reclaimed after lease expiry and complete without double-write.
- **Duplicate submission:** idempotency guarantees prevent duplicate rows and duplicate execution.
- **Database outage:** workers tolerate transient DB/DNS failures and resume processing after recovery.

See `drills/` for step-by-step commands and expected outcomes.


### Proof (local run)

```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"payload":{"fail_n_times":2},"idempotency_key":"proof-1"}'
# {"job_id":"6b356cc7-f8a4-4ca6-8227-0c3d57153559"}

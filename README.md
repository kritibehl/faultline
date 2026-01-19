# Faultline — Production-Grade Distributed Job Processing (Postgres-Leased)

Faultline is a durable job processing system built on **Postgres as the source of truth**.  
Workers claim jobs safely using **row-level locking** (`FOR UPDATE SKIP LOCKED`) and a **lease-based execution model** for crash recovery.

## Why this exists
Most hobby queues prove “it works once.” Faultline proves **it survives failures**:
- worker crashes mid-job
- duplicate submissions (idempotency)
- database outage + recovery

## Architecture
![Architecture](docs/architecture.png)

**Core idea:** jobs live in Postgres. Workers claim jobs by leasing rows.  
If a worker dies, the lease expires and another worker recovers the job.

## Features
- **Durable job state machine**: `queued → running → succeeded|failed`
- **Lease-based execution**: `lease_owner`, `lease_expires_at`
- **Crash recovery**: expired leases are re-claimed automatically
- **Hard idempotency**: idempotency key enforced at DB level
- **Retries w/ exponential backoff**: `next_run_at`, `attempts`, `max_attempts`
- **Terminal failure** after max attempts
- **Observability**: Prometheus metrics for API + worker
- **Failure drills**: scripted proof that the system recovers

## Quickstart
```bash
docker compose up -d --build
make migrate
curl http://localhost:8000/health

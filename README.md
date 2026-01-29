# Faultline — Production-Grade Distributed Job Processing System

Faultline is a PostgreSQL-backed distributed job processing system designed for **correctness under failure**.
It uses Postgres as the **source of truth**, with **lease-based execution** and **row-level locking**
(`FOR UPDATE SKIP LOCKED`) to provide crash-safe recovery and at-least-once execution semantics.


## Why This Exists

Many job queues demonstrate that jobs can run once.
Faultline is designed to demonstrate that jobs remain **correct, recoverable and observable** under real failure conditions, including:

- Worker crashes during execution
- Duplicate job submissions (idempotency)
- Database outages followed by recovery

## Architecture

![Architecture](docs/architecture.png)

Faultline uses PostgreSQL as the coordination layer and source of truth.

Workers atomically claim jobs by acquiring **time-bound leases** on job rows.
If a worker crashes mid-execution, the lease expires and another worker safely recovers the job.


## Core Design & Guarantees

Faultline provides the following guarantees:

- **Durable job state machine**  
  Jobs transition through explicit states: `queued → running → succeeded | failed`.

- **Lease-based execution**  
  Workers must hold a valid lease (`lease_owner`, `lease_expires_at`) to execute a job.

- **Crash-safe recovery**  
  Jobs with expired leases automatically become eligible for reprocessing.

- **Database-enforced idempotency**  
  Idempotency keys are enforced at the database level to prevent duplicate side effects.

- **Bounded retries with backoff**  
  Jobs retry using exponential backoff (`next_run_at`) and transition to a terminal failed state after `max_attempts`.

- **Explicit failure visibility**  
  Failures are surfaced through metrics rather than hidden retries.

## Observability

Faultline exposes Prometheus metrics for both the API and worker processes, including:

- Job throughput and execution latency
- Retry counts and failure rates
- Lease expirations and recovery events
- Queue depth and backlog growth

This makes failure modes and performance bottlenecks visible rather than implicit.

## Failure Validation

Faultline includes scripted failure drills that validate system behavior under:

- Worker termination during job execution
- Repeated job failures triggering retries
- Lease expiration and recovery by other workers

These drills demonstrate that the system recovers without manual intervention.

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


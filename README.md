# Faultline — Production-Grade Distributed Job Processing System

Faultline is a PostgreSQL-backed distributed job processing system designed for **correctness under failure** and adversarial timing.

It uses PostgreSQL as the **source of truth and coordination layer**, combining:

- **Lease-based execution**
- **Row-level locking** (`FOR UPDATE SKIP LOCKED`)
- **Fencing tokens for stale-writer protection**
- **Database-enforced idempotency**

to provide crash-safe recovery and deterministic execution semantics.

---

## Why This Exists

Many job queues demonstrate that jobs can run once.

Faultline is designed to demonstrate that jobs remain **correct, recoverable, race-safe, and observable** under real failure conditions, including:

- Worker crashes during execution  
- Lease-expiry races between concurrent workers  
- Duplicate job submissions (idempotency)  
- Database outages followed by recovery  
- Overlapping retries under contention  

The goal is not just execution — but **deterministic correctness under failure.**

---

## Architecture

![Architecture](docs/architecture.png)

Faultline uses PostgreSQL as the coordination layer and source of truth.

Workers atomically claim jobs by acquiring **time-bound leases** on job rows.
Each successful lease acquisition increments a monotonically increasing `fencing_token`.

If a worker crashes mid-execution, the lease expires and another worker safely recovers the job.
If a stale worker later attempts to write, it is rejected at the database boundary via fencing validation.

---

## Core Design & Guarantees

Faultline provides the following guarantees:

- **Durable job state machine**  
  Jobs transition through explicit states: `queued → running → succeeded | failed`.  
  Illegal transitions are rejected at the database layer.

- **Lease-based execution**  
  Workers must hold a valid lease (`lease_owner`, `lease_expires_at`) to execute a job.

- **Fencing-token stale-write protection**  
  Each lease increments a `fencing_token`.  
  Side effects are bound to `(job_id, fencing_token)` to prevent stale workers from committing after losing ownership.

- **Crash-safe recovery**  
  Jobs with expired leases automatically become eligible for safe reprocessing.

- **Database-enforced idempotency**  
  Side effects are protected by database uniqueness constraints to ensure at-most-once application per lease epoch.

- **Bounded retries with backoff**  
  Jobs retry using exponential backoff (`next_run_at`) and transition to a terminal failed state after `max_attempts`.

- **Explicit failure visibility**  
  Failures are surfaced through metrics rather than hidden retries.

---

## Deterministic Failure Validation

Faultline includes scripted failure drills that validate system behavior under:

- Worker termination during job execution  
- Lease expiration and recovery by another worker  
- Repeated job failures triggering retries  
- Stale-worker write attempts  

### Example Lease-Expiry Race

1. Worker A acquires lease (`token=1`)  
2. Lease expires  
3. Worker B reclaims job (`token=2`)  
4. Worker A attempts stale commit → rejected  
5. Worker B commits successfully  

This validates:

- Deterministic epoch advancement  
- Correct owner progression  
- Stale-write rejection  
- Exactly one successful side effect  

---

## Correctness Guarantees (Retry-Safe Ledger Semantics)

**Schema-backed invariant:** Each job may produce at most one ledger entry per lease epoch:


UNIQUE(job_id, fencing_token)


This binds side effects to the lease epoch, not just the job identifier.

Faultline enforces correctness at the database boundary so retries and crashes cannot violate invariants.

### Guarantees

- **Idempotent effects per lease epoch**  
  Each job is applied at most once per fencing token.

- **Atomic visibility**  
  Applying an effect and recording its ledger entry happens in a **single database transaction**, preventing partial state from becoming visible.

- **Stale-write rejection**  
  A worker holding an outdated fencing token cannot commit state.

- **Ordered state transitions**  
  Jobs follow a strict lifecycle. Illegal transitions are rejected.

- **Crash-safe reconciliation**  
  A reconciliation job repairs incomplete state after crashes by ensuring ledger state and job state converge.

---

### Supported Failure Scenarios

- Worker crash mid-execution  
- Worker crash mid-apply  
- Duplicate retries / duplicate submissions  
- Lease-expiry races  
- Partial writes (repaired by reconciliation)  
- Database restart and recovery  

---

### Invariants (informal)

- No duplicate ledger entries for the same `(job_id, fencing_token)`  
- A succeeded job must have exactly one corresponding ledger entry  
- A stale fencing token can never produce a successful state transition  
- Reconciliation eventually converges incomplete jobs to the correct terminal state  

---

## Observability

Faultline exposes Prometheus metrics for both the API and worker processes, including:

- Job throughput and execution latency  
- Retry counts and failure rates  
- Lease acquisitions, expirations, and recovery events  
- Stale-write rejections  
- Queue depth and backlog growth  

Failure modes and performance bottlenecks are measurable and visible rather than implicit.

---

## Tech Stack

- Python  
- PostgreSQL  
- Docker  
- Prometheus  

---

## Quickstart

```bash
docker compose up -d --build
make migrate
curl http://localhost:8000/health
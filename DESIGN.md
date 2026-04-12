# Faultline Design

Faultline is a correctness-first job execution system designed to guarantee exactly-once side effects under partial failure.

This document explains the design decisions and tradeoffs.

---

## Core Problem

In distributed job execution, the failure is not "a worker crashed".

The failure is:
> A worker crashes, loses its lease, another worker reclaims the job, and the original worker wakes up and commits late.

This produces **duplicate side effects**.

---

## Design Goal

Guarantee:

- No duplicate side effects (exactly-once commit)
- Eventual job completion under failure
- Deterministic rejection of stale work

---

## Why PostgreSQL as the coordination layer

Chosen because:

- Strong transactional guarantees
- Row-level locking semantics
- Enforceable invariants (UNIQUE, constraints)
- Single source of truth for correctness

Rejected:

- External queue brokers → obscure correctness boundary
- In-memory coordination → unsafe under crashes

---

## Why FOR UPDATE SKIP LOCKED

Used for concurrent job claiming.

Benefits:

- Avoids blocking workers
- Enables horizontal scaling
- Maintains deterministic ownership

Tradeoff:

- Polling-based model (not push-based)

---

## Why fencing tokens over heartbeat leases

### Problem with heartbeat leases

Lease-based systems assume:

> "If I still have the lease, I can commit."

But under failure:

- Worker A claims job (token=1)
- Worker A crashes / delays
- Lease expires
- Worker B claims job (token=2)
- Worker B commits
- Worker A wakes up → commits late

Result: **duplicate execution**

---

### Fencing token solution

Each claim increments a **monotonic fencing token**.

Rules:

- Only the **latest token** can commit
- Older tokens are rejected at the database layer

This transforms:

> "Who thinks they own the job"

into:

> "Who can prove they are the latest owner"

---

## Exactly-once enforcement

Faultline enforces:

- At-most-once commit (via ledger + fencing)
- Eventual completion (via retries + recovery)

Mechanisms:

- fencing token validation
- uniqueness constraints
- ledger-backed commit tracking

---

## Failure handling

### Reaper

Handles:
- expired leases
- crashed workers

Action:
- resets job → queued

---

### Reconciler

Handles:
- commit succeeded but job state not updated

Action:
- converges job → succeeded

---

## Fault Injection Strategy

Faultline explicitly tests:

- delayed execution beyond lease expiry
- worker crashes after claim
- stale worker wake-up
- concurrent claim races

Result:

- 0% duplicate commits across 1,500+ simulated failures
- naive systems exhibit measurable duplicate rates

---

## What Faultline does NOT solve

Faultline intentionally does not attempt:

- Byzantine fault tolerance
- multi-region consensus
- coordinator availability guarantees
- external side-effect idempotency

This is a **single-coordinator correctness system**, not a consensus system.

---

## Design Philosophy

Faultline prioritizes:

- correctness over throughput
- explicit invariants over assumptions
- database-enforced guarantees over application logic

---

## Key Insight

Failures are not about crashes.

Failures are about **incorrect recovery after crashes**.

Faultline enforces correctness at the point where recovery happens.

# Designing Against Lease Expiry Races: A Deterministic Failure Analysis

Status: Development adversarial test failure (no production impact)  
Environment: Local + CI deterministic harness  
Component: Lease-based execution model (Faultline)

---

## Summary

During adversarial testing of the lease-based execution model, a race between lease expiry and worker resumption produced stale state mutation that database-level idempotency alone did not prevent.

The failure was constructed deterministically using a barrier-orchestrated harness and resolved by introducing fencing tokens bound to lease acquisition order.

This document describes the failure construction, root cause, and corrective measures.

---

## System Context

Faultline coordinates distributed workers processing jobs from a shared PostgreSQL-backed queue.

Each job:

- Is claimed via a lease with a time-to-live (TTL)
- Transitions from `queued → running`
- Can be reclaimed when `lease_expires_at < NOW()`

The original design relied on:

- PostgreSQL transactional guarantees
- Idempotency keyed on `job_id`
- Worker termination after lease expiry

The system assumed lease expiry and worker termination were effectively synchronous. They are not.

---

## Failure Construction

The failure was engineered deliberately using a deterministic harness.

Sequence enforced by the harness:

1. Worker A acquires a lease with a 1-second TTL.
2. Worker A is artificially delayed 2.5 seconds, forcing lease expiry.
3. A barrier prevents Worker B from claiming until Worker A’s lease has expired.
4. Worker B acquires the lease and begins execution.
5. Worker A resumes briefly before termination and attempts state mutation under a now-invalid lease.

Without fencing tokens, the system had no mechanism to distinguish Worker A’s stale lease from Worker B’s valid one.

PostgreSQL prevented duplicate final commits, but it did not prevent intermediate state mutation before Worker A was terminated.

Structured trace captured during reproduction:


stale_write_blocked | stale_token: 1 | current_token: 2 | reason: token_mismatch


This confirmed the failure was deterministic and reproducible.

---

## Root Cause

Idempotency was keyed only on `job_id`.

This prevented duplicate rows but did not encode lease epoch ownership.

When a lease expires and a new worker claims the job:

- The previous worker receives no database-level signal that its lease is invalid.
- Lease expiry and worker termination operate in separate failure domains.
- Transactional integrity alone does not enforce temporal ownership.

The system lacked a monotonic ownership primitive.

---

## Contributing Factors

- No fencing token in the original lease design.
- Idempotency testing covered sequential retries but not overlapping lease claims.
- Clock skew during crash injection exceeded assumed tolerance (<1s), reaching ~2s.
- Retry logic assumed monotonic attempt ordering without enforcing it.
- Invariant checks validated final state but did not gate intermediate mutation paths.

---

## Corrective Actions

Three changes resolved the issue.

### 1. Introduced Fencing Tokens

A `fencing_token` increments atomically on every lease acquisition.

This establishes monotonic ownership of a job.

### 2. Rebound Idempotency Keys

Idempotency keys changed from:


(job_id)


to:


(job_id, fencing_token)


Writes are now bound to a specific lease epoch.

### 3. Added Write Gate

A mandatory `assert_fence()` check was introduced before every state mutation.

Writes are rejected when:


worker_token != current_fencing_token


Claim SQL:

```sql
UPDATE jobs
SET state = 'running',
    fencing_token = fencing_token + 1
WHERE id = $1
  AND (
        state = 'queued'
        OR (state = 'running' AND lease_expires_at < NOW())
      )
RETURNING fencing_token;
Validation

The adversarial harness was rerun under identical conditions:

500 deterministic runs

Forced lease expiry

Crash injection

Artificial clock skew

Results:

Zero stale mutations

All intermediate invalid writes rejected

Transitional invariants preserved

What Worked

Deterministic replay tooling reconstructed exact event ordering.

Invariant checks surfaced inconsistencies immediately.

The failure remained contained within development infrastructure.

The harness made the fix measurable and verifiable.

Preventative Measures

Fencing token enforcement is mandatory for all lease-based coordination.

Crash injection and forced lease expiry run automatically in CI.

Lease overlap anomaly detection integrated into monitoring.

Deterministic replay enabled for concurrency-critical paths.

Lessons

Lease mechanisms without fencing tokens are incomplete in multi-worker systems.

Database idempotency does not eliminate intermediate mutation risk.

Lease expiry and worker termination must be treated as independent failure domains.

Clock skew is an expected condition, not an edge case.

Transitional invariants must be validated, not only final state correctness.

Deterministic adversarial testing exposes concurrency paths that unit tests miss.

Closing Note

This failure was intentionally constructed under adversarial timing conditions to validate coordination guarantees. No production systems were impacted.

The fencing-token enforcement model is now required for all lease-based execution paths.
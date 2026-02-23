# Designing Against Lease Expiry Races: A Deterministic Failure Analysis

Status: Development adversarial test failure (no production impact)  
Environment: Local + CI deterministic harness  
Component: Lease-based execution model (Faultline)

---

## Summary

During adversarial testing of the lease-based execution model, we identified a race condition between lease expiry and worker resumption. A stale worker was able to attempt state mutation even after another worker had legally reclaimed the job.

Database-level idempotency prevented duplicate terminal state transitions, but it did not prevent stale intermediate updates under an expired lease.

The issue was reproduced deterministically and resolved by introducing fencing tokens tied to lease acquisition order.

---

## System Context

Faultline uses PostgreSQL as the coordination layer for distributed workers.

Each job:

- Is claimed using a time-bound lease (TTL)
- Transitions from `queued → running`
- Can be reclaimed when `lease_expires_at < NOW()`

The original design relied on:

- PostgreSQL transactional guarantees
- Idempotency keyed only on `job_id`
- The assumption that lease expiry and worker termination occur together

That assumption was incorrect.

Lease expiry and worker termination are independent failure domains.

---

## Failure Construction

The issue was intentionally constructed using a deterministic harness.

The sequence was:

1. Worker A acquired a lease with a 1-second TTL.
2. Worker A was delayed 2.5 seconds to force lease expiry.
3. A barrier prevented Worker B from claiming the job until Worker A’s lease had expired.
4. Worker B acquired the lease and began execution.
5. Worker A resumed briefly and attempted a state mutation under its expired lease.

Without additional safeguards, the system could not distinguish Worker A’s stale claim from Worker B’s valid one.

PostgreSQL prevented duplicate final commits. However, it did not prevent stale intermediate writes before Worker A was terminated.

Structured trace during reproduction:


stale_write_blocked | stale_token: 1 | current_token: 2 | reason: token_mismatch


This confirmed the issue was deterministic and reproducible.

---

## Root Cause

Idempotency was keyed only on `job_id`.

This prevented duplicate ledger entries but did not encode lease ownership over time.

When a lease expires and a new worker reclaims the job:

- The previous worker receives no database-level signal that its lease is invalid.
- Transactional integrity does not enforce temporal ownership.
- Lease expiry does not automatically invalidate in-flight execution.

The system lacked a monotonic ownership mechanism.

---

## Contributing Factors

- No fencing token in the initial lease design.
- Tests covered sequential retries but not overlapping lease claims.
- Clock skew during crash injection exceeded expected tolerance.
- Retry logic assumed monotonic attempt ordering without enforcing it.
- Invariants validated final state but did not gate intermediate writes.

---

## Corrective Actions

Three changes resolved the issue.

### 1. Introduced Fencing Tokens

A `fencing_token` is incremented atomically each time a lease is acquired.

This establishes monotonic ownership of the job.

### 2. Rebound Idempotency Keys

Idempotency keys changed from:


(job_id)


to:


(job_id, fencing_token)


This binds writes to a specific lease epoch.

### 3. Added a Write Gate

A required `assert_fence()` check was added before all state mutations.

Writes are rejected when:


worker_token != current_fencing_token


Lease claim SQL:

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
```

## Validation

The deterministic harness was rerun under identical conditions:

- 500 runs
- Forced lease expiry
- Crash injection
- Artificial clock skew

### Results

- Zero stale mutations
- All invalid writes correctly rejected
- Transitional invariants preserved
- No race window was observed after fencing enforcement

---

## Preventative Measures

- Fencing token enforcement is now mandatory for all lease-based paths.
- Crash injection and forced lease expiry are part of CI.
- Lease overlap detection added to monitoring.
- Deterministic replay enabled for concurrency-critical code paths.

---

## Lessons

- Lease-based systems require fencing tokens in multi-worker environments.
- Database idempotency does not eliminate intermediate mutation risk.
- Lease expiry and worker termination must be treated separately.
- Systems must validate ownership at mutation time, not just at commit time.
- Clock skew should be assumed, not ignored.
- Transitional invariants are as important as final state checks.

---

## Closing Note

This failure was intentionally constructed under adversarial timing conditions to validate correctness guarantees. No production systems were impacted.
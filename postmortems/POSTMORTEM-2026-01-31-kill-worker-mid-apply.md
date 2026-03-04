# Postmortem: Duplicate Submission Under Concurrent Retry

**Scenario:** Two identical job submissions race past the application-layer
idempotency check simultaneously  
**Severity:** Would be P1 in production (duplicate payment, duplicate email, etc.)  
**Status:** Invariant holds — database-layer uniqueness constraint provides
race-safe fallback

---

## The Race Window

The application-layer idempotency check in `create_job()` is:

```python
existing = db.query(Job).filter_by(idempotency_key=key).first()
if existing:
    return existing  # return early
# ... INSERT new job
```

This check has a race window. Two requests with the same `idempotency_key`
can both read `existing = None` simultaneously (before either INSERT commits),
then both attempt to INSERT:

```
Request 1: SELECT → None
Request 2: SELECT → None
Request 1: INSERT (job_id=A) → succeeds
Request 2: INSERT (job_id=B) → would succeed without DB constraint
```

Without a database-level constraint, both INSERTs succeed, producing two
job rows with the same idempotency key.

---

## Why Application-Layer Checks Are Insufficient

The SELECT → check → INSERT pattern is not atomic. Any concurrent request
can observe the same empty state and proceed to INSERT. This is the classic
TOCTOU (time-of-check time-of-use) race.

Mitigations like `SELECT FOR UPDATE` or advisory locks add contention and
complexity without eliminating the fundamental problem for new keys.

The only correct solution is a database-level uniqueness constraint.

---

## The Fix: Two-Layer Defence

### Layer 1: Application check (fast path)
```python
existing = db.query(Job).filter_by(idempotency_key=key).first()
if existing:
    return existing  # no INSERT attempted
```
This handles the common case (genuine duplicate, retrying client) efficiently.

### Layer 2: Database constraint (race-safe fallback)
```sql
CREATE UNIQUE INDEX uq_jobs_idempotency_key
  ON jobs(idempotency_key)
  WHERE idempotency_key IS NOT NULL;
```

If two requests race past Layer 1 simultaneously, exactly one INSERT succeeds.
The other gets an `IntegrityError`, which is caught and handled:

```python
except IntegrityError:
    db.rollback()
    existing = db.query(Job).filter_by(idempotency_key=key).first()
    return existing  # return the winner's row
```

This pattern is correct under all concurrency conditions.

---

## Payload Hash Mismatch

A separate concern: the same `idempotency_key` reused with a different payload.
This is likely a client bug (wrong key, wrong payload) and should be surfaced
explicitly rather than silently returning the wrong job.

Faultline stores `payload_hash` on job creation and compares it on duplicate
submissions:

```python
if existing.payload_hash != _payload_hash(body.payload):
    raise HTTPException(status_code=409, detail="Idempotency key reused with different payload")
```

This catches the case where a client reuses a key across different operations.

---

## Timeline

```
T0  Client submits job_id=X with idempotency_key=K and payload=P
T1  API: SELECT WHERE idempotency_key=K → None
T2  Client times out, retries
T3  API (original): INSERT job (id=A, key=K, hash=H(P)) → COMMITTED
T4  API (retry):   SELECT WHERE idempotency_key=K → finds row A
T5  API (retry):   hash(P) == existing hash ✓ → return job A

Result: one job row, same job_id returned to client on both attempts.
```

---

## Concurrent Race Timeline

```
T0  Request 1: SELECT WHERE key=K → None
T0  Request 2: SELECT WHERE key=K → None  (concurrent)
T1  Request 1: INSERT (id=A, key=K) → COMMITTED
T1  Request 2: INSERT (id=B, key=K) → IntegrityError (unique violation)
T2  Request 2: catches IntegrityError, rolls back
T3  Request 2: SELECT WHERE key=K → finds row A
T4  Request 2: returns job A

Result: one job row, both requests return the same job_id.
```

---

## Invariants Confirmed

| Invariant | Mechanism | Status |
|-----------|-----------|--------|
| No duplicate job rows per idempotency key | `UNIQUE INDEX uq_jobs_idempotency_key` | ✅ |
| Concurrent duplicates handled correctly | `IntegrityError` catch + re-query | ✅ |
| Payload mismatch surfaced explicitly | payload_hash comparison → 409 | ✅ |
| Application check handles common case efficiently | SELECT before INSERT | ✅ |

---

## Validated By

`drills/02_duplicate_submission/README.md` — manual drill  
`make drill-02` — automated drill with assertions
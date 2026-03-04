# Postmortem: Worker Crash Mid-Apply — Reconciler Recovery

**Scenario:** Worker commits ledger entry, crashes before updating `jobs.state`  
**Severity:** Would be P1 in production (job stuck in `running` forever without reconciler)  
**Status:** Invariant holds — reconciler converges state within `RECONCILE_SLEEP_SECONDS`

---

## The Crash Window

`mark_succeeded()` performs two sequential writes:

```sql
-- Write 1: ledger entry (idempotency boundary)
INSERT INTO ledger_entries (job_id, fencing_token, ...) VALUES (...)
ON CONFLICT (job_id, fencing_token) DO NOTHING;

-- Write 2: state transition
UPDATE jobs SET state='succeeded' WHERE id=... AND fencing_token=...;
```

If the worker process is killed between Write 1 committing and Write 2 executing,
the job is permanently in an inconsistent state:

```
ledger_entries: (job_id=X, fencing_token=2)  ← exists
jobs:           state='running'               ← stuck
```

Without intervention, this job will be reaped by the lease expiry logic and
retried — but `ON CONFLICT DO NOTHING` will silently skip the duplicate ledger
write. The retry will succeed the second time, producing correct final state.

**However:** this means the job's side effect runs twice at the application layer,
even though the ledger only records it once. For true exactly-once semantics at
the application layer, the reconciler provides a faster path.

---

## Reconciler Recovery

`services/worker/reconciler.py::reconcile_once()` detects this condition:

```sql
SELECT j.id
FROM jobs j
JOIN ledger_entries l ON l.job_id = j.id
WHERE j.state <> 'succeeded'
```

Any job with a committed ledger entry that hasn't reached `succeeded` is
converged immediately, without re-executing the job. This is the fast path.

---

## Timeline

```
T0  Worker claims job → fencing_token=2
T1  assert_fence() passes
T2  Job executes
T3  assert_fence() passes
T4  INSERT INTO ledger_entries (job_id=X, token=2) → COMMITTED ✓
T5  CRASH (os._exit, OOM kill, network loss, etc.)
    UPDATE jobs SET state='succeeded' → NEVER RUNS

    --- time passes ---

T6  Reconciler wakes (every RECONCILE_SLEEP_SECONDS=5s)
T7  Finds (job_id=X, state='running', ledger entry exists)
T8  UPDATE jobs SET state='succeeded' WHERE id=X → COMMITTED ✓

    Result: job converged to succeeded. No re-execution.
```

---

## Drill Validation

Drill `drills/drill_kill_worker_mid_apply.sh` validates this scenario:

1. Start worker with `CRASH_AT=before_commit`
2. Worker commits ledger entry, then `os._exit(137)`
3. Assert job is stuck in `running` with committed ledger entry
4. Start reconciler
5. Assert job transitions to `succeeded` within `RECONCILE_SLEEP_SECONDS * 2`
6. Assert exactly one ledger entry

---

## Invariants Confirmed

| Invariant | Mechanism | Status |
|-----------|-----------|--------|
| No job permanently stuck after crash | Reconciler JOIN on ledger_entries | ✅ |
| No duplicate ledger entries on retry | `ON CONFLICT DO NOTHING` | ✅ |
| State convergence within bounded time | `RECONCILE_SLEEP_SECONDS` TTL | ✅ |
| Reconciler is idempotent | FOR UPDATE SKIP LOCKED + WHERE clause | ✅ |

---

## Key Insight

The ledger entry is the durable proof of work. Once it exists for a given
`(job_id, fencing_token)`, the job's result is committed regardless of whether
`jobs.state` reflects it yet. The reconciler simply observes this proof and
updates the view.

This separates durability (ledger) from visibility (jobs.state) — and the
reconciler bridges the gap when the worker can't.
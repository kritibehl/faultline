# Postmortem: Worker killed mid-apply (Crash Window)

**Date:** 2026-01-31  
**System:** Faultline  
**Scenario:** Worker terminated while processing a job (mid-apply)

## Summary
We simulated a worker crash during job execution to validate that Faultline preserves correctness under failure. The system must not duplicate effects and must converge job state correctly after recovery.

## Impact
- No user-visible data loss expected (jobs persisted in DB).
- Risk being tested: inconsistent state where an effect is applied but job state is not updated.

## What Happened (Timeline)
- Seeded a queued job into Postgres.
- Worker claimed the job (state transitioned to `running` with a lease).
- Worker was killed before it could complete normally.
- Reconciler ran and repaired incomplete state by converging job state based on ledger presence.

## Root Cause (of the risk)
A crash can occur in the window between:
1) effect application (ledger entry creation)
2) job state update (`running → succeeded`)

## Detection
- Verified job and ledger state via Postgres queries.
- Metrics available: jobs succeeded, retries, worker heartbeats.

## Resolution
- Enforced idempotency at the DB boundary (`ledger_entries.job_id UNIQUE`).
- Added reconciler to converge job state to `succeeded` when a ledger entry exists.

## Correctness Guarantees Validated
- At-most-once effect application (idempotent ledger insert).
- Crash-safe recovery through reconciliation convergence.
- No duplicate ledger entries after retries/restarts.

## Follow-ups
- Add CI hook to run reconciliation tests.
- Add one more drill for DB outage during job processing (future).

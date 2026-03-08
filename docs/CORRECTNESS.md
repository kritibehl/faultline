# Faultline — Correctness Guarantees

## Invariant Table

| # | Invariant | Mechanism | Validated by |
|---|-----------|-----------|--------------|
| I1 | No stale owner may commit | `assert_fence()` checks `fencing_token` and `lease_expires_at` | 500-run race harness |
| I2 | No duplicate side effect | `UNIQUE(job_id, fencing_token)` on `ledger_entries` | `test_lease_race_fencing.py` |
| I3 | Reclaimed owner supersedes expired | `fencing_token` increments atomically on every claim | S04 drill |
| I4 | Crash recovery converges | Reconciler detects `state=running` + committed ledger | S07 drill |
| I5 | Bounded retries with backoff | `mark_for_retry()` + `backoff_seconds(attempts)` | `test_retry_backoff.py` |

## Proof Block

| Fault | What happens | Outcome |
|-------|--------------|---------|
| Lease expiry under active worker | `assert_fence()` sees `lease_expired`; write blocked | Successor commits; ledger count = 1 |
| Worker crash before side effect | Lease expires; successor reclaims with `token+1` | Exactly one commit |
| Worker crash after side effect | Reconciler finds committed ledger entry | Sets `succeeded`; no second write |
| Concurrent reclaim race | `FOR UPDATE SKIP LOCKED` serializes claims | One valid owner; zero duplicates |
| Duplicate submission | App check + `UNIQUE` on `idempotency_key` | Same `job_id`; one DB row |
| Exhausted retries | `attempts >= max_attempts` | `state=failed`; not requeued |

## Race Results: 500 Runs

| Metric | Result |
|--------|--------|
| Runs completed | 500/500 |
| Stale writes blocked | 500/500 |
| Duplicate ledger entries | 0 |
| Jobs succeeded exactly once | 500/500 |

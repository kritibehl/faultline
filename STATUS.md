# Faultline — Implementation Status

Maps every claim in the positioning matrix to its exact implementation,
the mechanism enforcing it, and the test validating it.

---

## 🔵 Backend SWE

| Claim | File | Function / Location | Mechanism |
|-------|------|---------------------|-----------|
| Lease-based coordination via `FOR UPDATE SKIP LOCKED` | `services/worker/worker.py` | `claim_one_job()` production path | PostgreSQL row-level locking; workers skip locked rows without blocking each other |
| Atomic lease acquisition (`UPDATE … RETURNING fencing_token`) | `services/worker/worker.py` | `claim_one_job()` | Single `UPDATE … SET fencing_token+1 … RETURNING` — no gap between read and write |
| DB-enforced idempotency via uniqueness constraints | `migrations/011_bind_ledger_to_fencing_token.sql` | `uq_ledger_entries_job_fence` | `UNIQUE(job_id, fencing_token)` on `ledger_entries`; `ON CONFLICT DO NOTHING` in `mark_succeeded()` |
| Correctness validated across 500 controlled runs | `tests/test_lease_race_fencing.py` | `test_lease_expiry_race_is_blocked_by_fencing()` | 500-run barrier-coordinated harness; asserts 0 duplicate executions |
| Crash reconciliation for mid-execution termination | `services/worker/reconciler.py` | `reconcile_once()` | Joins `jobs` to `ledger_entries`; converges state without re-execution |

---

## 🔵 Infra / Distributed Systems

| Claim | File | Function / Location | Mechanism |
|-------|------|---------------------|-----------|
| Lease ownership epochs via fencing tokens per acquisition | `migrations/010_add_fencing_token.sql`, `services/worker/worker.py` | `claim_one_job()` | `fencing_token BIGINT` incremented atomically on every claim |
| Invariant-based write gating (`assert_fence`) | `services/worker/worker.py` | `assert_fence()` | Reads current token + lease expiry inside same transaction; raises `RuntimeError("stale_token")` or `RuntimeError("lease_expired")` |
| Deterministic concurrency reproduction harness | `tests/test_lease_race_fencing.py` | `_run_once()` + barrier env vars | `BARRIER_OPEN` / `BARRIER_WAIT` via `barriers` table; `LEASE_SECONDS=1` forces expiry during A's 2.5s sleep |
| No duplicate side effects under concurrent retry | `tests/test_lease_race_fencing.py`, `tests/test_idempotent_apply.py` | per-run ledger count assertion | `ON CONFLICT DO NOTHING` + `UNIQUE(job_id, fencing_token)` |
| Ownership correctness invariants via controlled failure scenarios | `tests/test_lease_race_fencing.py`, `postmortems/` | 5 invariant checks per run | stale_blocked, b_succeeded, job state, ledger count, token monotonicity |

---

## 🔵 DevOps / SRE

| Claim | File | Function / Location | Mechanism |
|-------|------|---------------------|-----------|
| Crash-safe reconciliation ensuring state convergence | `services/worker/reconciler.py` | `reconcile_once()` | Ledger JOIN detects committed-but-not-succeeded jobs; `FOR UPDATE SKIP LOCKED` allows concurrent reconciler replicas |
| Structured invariant-validation logs for ownership violations | `common/logging.py`, `services/worker/worker.py` | `log_event()`, `log_stale_write()` | JSON-structured lines with `event`, `job_id`, `fencing_token`, `reason`, `severity` |
| Explicit failure states to reduce recovery ambiguity | `common/states.py`, `migrations/005_add_jobs_state_check.sql` | `JobState` enum | `queued → running → succeeded \| failed`; illegal transitions blocked by CHECK constraint |
| Expired lease reaper | `worker/reaper.py` | `reap_expired_leases()` | Scans `state='running' AND lease_expires_at < NOW()`; resets to `queued` |
| Prometheus metrics for all failure modes | `services/worker/worker.py`, `services/api/app.py` | `stale_commits`, `jobs_succeeded`, etc. | `prometheus_client` counters; scraped via `/metrics` |

---

## 🔵 Payments / Exactly-Once Systems

| Claim | File | Function / Location | Mechanism |
|-------|------|---------------------|-----------|
| Epoch-bound idempotency via `(job_id, fencing_token)` uniqueness | `migrations/011_bind_ledger_to_fencing_token.sql` | `uq_ledger_entries_job_fence` | DB-layer constraint; holds regardless of application code path |
| No duplicate side effects under concurrent lease expiry | `tests/test_lease_race_fencing.py` | per-run `_ledger_info()` assertion | 500 runs × 0 duplicates |
| Atomic visibility: effect + state in one transaction | `services/worker/worker.py` | `mark_succeeded()` | `INSERT ledger_entries` + `UPDATE jobs` in same `psycopg2` transaction; `conn` context manager commits on success |
| Stale fencing token never produces successful state transition | `services/worker/worker.py` | `assert_fence()` + `mark_succeeded()` WHERE clause | Two-layer gate: application (`assert_fence`) + DB (`fencing_token=%s` in UPDATE) |

---

## Validated Invariants

1. `UNIQUE(job_id, fencing_token)` on `ledger_entries` — enforced at DB layer
2. A succeeded job always has exactly one ledger entry — validated by reconciler + tests
3. A stale fencing token never produces a successful state transition — `assert_fence()` + WHERE clause
4. State convergence after crash — reconciler + reaper cover both crash windows
5. Illegal state transitions rejected — `jobs_state_check` constraint + enum guard
6. Concurrent claim safety — `FOR UPDATE SKIP LOCKED` in `claim_one_job()`
7. 0 duplicate executions across 500 controlled runs — `test_lease_race_fencing.py`

---

## Test Coverage

| Test | What It Validates |
|------|-------------------|
| `tests/test_lease_race_fencing.py` | Fencing token blocks stale writes; 500-run deterministic harness |
| `tests/test_idempotent_apply.py` | `ON CONFLICT DO NOTHING` prevents duplicate ledger entries |
| `tests/test_reconciler.py` | Reconciler converges committed-but-not-succeeded jobs |

---

## Run It

```bash
docker compose up -d --build
make migrate
pytest tests/ -v
```
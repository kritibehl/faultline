# Changelog

All notable changes to Faultline are documented here.

---

## [1.1.0] — 2026-03-03

### Fixed
- **Critical:** Removed redundant `lease_expires_at > NOW()` check from
  `mark_succeeded()` WHERE clause. This check caused false `stale_commit`
  rejections when a short lease (1s in tests) expired in the microseconds
  between `assert_fence()` passing and the UPDATE executing. `assert_fence()`
  already validates the lease in the same transaction — the redundant check
  added latency risk with no correctness benefit. The `fencing_token` match
  in the WHERE clause is the correctness boundary.

### Validated
- 500-run deterministic race harness passes with 0 failures, 0 duplicate
  executions, stale writes blocked 500/500.

---

## [1.0.0] — 2026-01-31

### Added
- Lease-based job claiming via `FOR UPDATE SKIP LOCKED` — workers claim
  jobs atomically without blocking each other.
- Fencing tokens: each lease acquisition increments a monotonic counter.
  Stale workers holding an old token are rejected at the DB boundary.
- `assert_fence()` write gate — called before every state mutation to
  validate the worker holds the current epoch.
- `UNIQUE(job_id, fencing_token)` on `ledger_entries` — DB-layer
  idempotency enforcement that holds even if application code is bypassed.
- `ON CONFLICT DO NOTHING` in `mark_succeeded()` — idempotent ledger writes.
- Reconciler process (`services/worker/reconciler.py`) — converges jobs
  whose ledger entry was committed but `jobs.state` was not updated (mid-apply
  crash recovery).
- Barrier coordination (`BARRIER_WAIT` / `BARRIER_OPEN` env vars + `barriers`
  table) — deterministic timing control for concurrency tests.
- Structured JSON logging via `log_event()` — every ownership event, lease
  transition, and fence violation is machine-parseable.
- Prometheus metrics: `faultline_jobs_claimed_total`,
  `faultline_jobs_succeeded_total`, `faultline_stale_commit_prevented_total`,
  `faultline_worker_heartbeat_total`.
- Idempotency key on job submission — duplicate submissions return the
  existing job, protected by `UNIQUE INDEX` with race-safe fallback.
- Crash injection via `CRASH_AT` env var — `after_lease_acquire` and
  `before_commit` injection points for drill scenarios.
- Three failure drills: worker crash, duplicate submission, DB outage.
- Autopsy log path (`AUTOPSY_LOG_PATH`) — structured log capture for
  post-hoc forensics.
- `make lease-race-500` — 500-run race harness with per-run invariant
  assertions and results written to `tests/results/lease_race_500_runs.txt`.

### Schema
- `jobs.fencing_token BIGINT NOT NULL DEFAULT 0`
- `jobs.idempotency_key TEXT` with unique index
- `jobs.payload_hash TEXT`
- `ledger_entries(job_id, fencing_token)` unique index
- `barriers(name)` table for deterministic test coordination
- `ck_jobs_state` CHECK constraint enforcing valid state transitions

### Tests
- `test_lease_race_fencing.py` — deterministic two-worker race, 500 runs
- `test_idempotent_apply.py` — `UNIQUE(job_id, fencing_token)` constraint
- `test_reconciler.py` — reconciler convergence logic

---

## [0.1.0] — 2026-01-15

### Added
- Initial project scaffolding
- Defined scope and system boundaries (`SCOPE.md`)
- Basic jobs table, worker loop, API skeleton
# Faultline

**A crash-safe distributed job execution engine with formal correctness guarantees.**

Faultline solves the hardest class of distributed systems bugs: what happens when a worker dies mid-execution, a lease expires while a job is running, or two workers race to claim the same job? Most job queues paper over these with timeouts and hope. Faultline proves correctness through fencing tokens, formal invariants, and 500-run deterministic race reproduction.

```bash
make drill-all    # 29/29 failure scenarios pass
```

---

## Why this is hard

A distributed job queue must answer one question correctly under every failure mode:

> **Exactly which worker committed the side effect for job J?**

Get it wrong and you get duplicate payments, double-sent emails, or corrupted state. The naive solutions all fail:

| Approach | Failure mode |
|----------|-------------|
| Heartbeat + timeout | Worker A times out, B claims, A recovers and commits — **two commits** |
| Optimistic locking | Clock skew makes "last write wins" unpredictable |
| Distributed lock service | Lock server becomes single point of failure |
| At-least-once + idempotency key | Key collision on different payloads → silent data loss |

Faultline's answer: **fencing tokens**. Every claim increments a monotone counter. Every commit verifies the token matches. A stale worker's token is permanently invalid — not just for a window, but forever.

---

## Correctness proof

Five formal invariants enforced on every job:

| ID | Invariant | Enforcement |
|----|-----------|-------------|
| I1 | No stale owner may commit | `assert_fence` checks `fencing_token` before every write |
| I2 | No duplicate side effect for the same logical job | `UNIQUE(job_id, fencing_token)` in `ledger_entries` |
| I3 | Fencing token is strictly monotone after reclaim | `UPDATE ... SET fencing_token = fencing_token + 1` on reclaim |
| I4 | Crash recovery converges to exactly one valid outcome | Reconciler promotes `committed-but-not-succeeded` jobs |
| I5 | No two workers hold an active lease simultaneously | `SELECT FOR UPDATE SKIP LOCKED` + lease expiry enforcement |

Validated across **500 deterministic race reproductions**:

```
[500/500] passed=500 failed=0 stale_blocked=500 duplicate_ledger=0
```

---

## How fencing tokens work

```
t=0.0s  Worker A claims job J
          fencing_token = 1
          lease_expires_at = now + 5s

t=0.1s  Worker A begins execution (takes 7s)

t=5.0s  Lease expires — A is still running

t=5.1s  Worker B reclaims J
          fencing_token = 2          ← monotone increment
          lease_expires_at = now + 30s

t=5.2s  Worker B executes, commits
          INSERT ledger_entries (job_id=J, fencing_token=2)
          UPDATE jobs SET state='succeeded' WHERE fencing_token=2

t=7.0s  Worker A wakes, tries to commit
          assert_fence: SELECT fencing_token FROM jobs WHERE id=J → 2
          held token=1 ≠ current token=2 → StaleWriteBlocked raised
          logged: {"event": "stale_write_blocked", "held": 1, "current": 2}

Result: exactly 1 ledger entry, exactly 1 commit, zero duplicates.
```

Two independent defense layers — either one alone prevents the duplicate:
1. **Application layer**: `assert_fence` raises before the write reaches the DB
2. **Database layer**: `UNIQUE(job_id, fencing_token)` rejects the insert even if the application check is bypassed

---

## Failure scenario matrix

29 assertions across 16 failure scenarios, all passing:

| Scenario | Fault injected | Key assertion |
|----------|---------------|---------------|
| S01 | Worker crashes after ledger insert, before state update | Reconciler promotes to `succeeded`, 1 ledger entry |
| S02 | Worker crashes before commit — claim never persisted | Job recovered, no phantom claim |
| S03 | Lease TTL expires mid-execution (1s lease, 2.5s sleep) | B reclaims, exactly 1 ledger entry |
| S04 | Stale worker holds old token, tries to commit after reclaim | Token mismatch → write rejected |
| S05 | Duplicate submission with same idempotency key | Both requests return same `job_id` |
| S06 | Same idempotency key, different payload | 409 Conflict returned |
| S07 | Job has ledger entry but `state=running` (mid-apply crash) | Reconciler converges without duplicating |
| S08 | `max_attempts=1`, job fails on first attempt | `state=failed`, `attempts=1` |
| S09 | Job fails, gets rescheduled with exponential backoff | `next_run_at` set, succeeds on retry |
| S10 | 10 concurrent submissions with same idempotency key | Exactly 1 job row created |
| S11 | Direct DB test: duplicate `(job_id, fencing_token)` insert | UNIQUE constraint blocks second insert |
| S12 | Worker killed mid-batch (3 jobs), new worker picks up | All 3 jobs succeed, no loss |
| S13 | Job stuck in `running` with expired lease | Reaper resets to `queued` |
| S14 | DB connectivity check | `/health` returns `status=ok` |
| S15 | Queue state counts | `/queue/depth` reflects actual DB counts |
| S16 | Nonexistent job lookup | Returns 404 |

---

## Scenario runner

7 fault scenarios with structured output and HTML reports:

```bash
python3 services/cli/scenario_runner.py all --report
```

```
============================================================
  Faultline Scenario Runner
============================================================
-- lease-expiry: worker sleeps past TTL, successor reclaims --
  PASS: job succeeded
  PASS: exactly 1 ledger entry
  [PASS] lease-expiry — 2/2 checks (6.3s)
-- worker-crash: crash before commit, successor recovers --
  PASS: crash injected
  PASS: job succeeded
  PASS: exactly 1 ledger entry
  [PASS] worker-crash — 3/3 checks (3.4s)
-- reclaim-race: concurrent workers, exactly one commits --
  PASS: job succeeded
  PASS: exactly 1 ledger entry
  [PASS] reclaim-race — 2/2 checks (2.5s)
-- retry-backoff: failure triggers backoff, succeeds on retry --
  PASS: re-queued after failure
  PASS: attempts incremented
  PASS: next_run_at set (backoff active)
  PASS: succeeded on retry
  PASS: 1 ledger entry
  [PASS] retry-backoff — 5/5 checks (0.3s)
-- max-retries: exhausts attempts, state=failed --
  PASS: state=failed
  PASS: attempts=1
  PASS: error recorded
  [PASS] max-retries — 3/3 checks (2.2s)
-- db-timeout: worker survives transient connection loss --
  PASS: job completed successfully
  PASS: exactly 1 ledger entry
  PASS: no unhandled traceback
  [PASS] db-timeout — 3/3 checks (0.2s)
-- network-interruption: short lease simulates cut-off worker --
  PASS: job recovered after interruption
  PASS: exactly 1 ledger entry
  [PASS] network-interruption — 2/2 checks (7.9s)
============================================================
  Results: 7/7 scenarios passed
============================================================
```

---

## Lease lifecycle

```
                    ┌──────────────────────────────────┐
                    │             queued               │
                    │     next_run_at <= NOW()         │
                    └───────────────┬──────────────────┘
                                    │ SELECT FOR UPDATE SKIP LOCKED
                                    │ fencing_token += 1
                                    ▼
                    ┌──────────────────────────────────┐
                    │             running              │
                    │   lease_owner   = worker_id      │
                    │   lease_expires_at = now + TTL   │
                    └──┬───────────────────────┬───────┘
                       │                       │
              execute OK                 lease expires
              assert_fence passes        reaper fires
                       │                       │
                       │              fencing_token += 1
                       │              state → queued
                       ▼                       │
          ┌─────────────────────┐              │ (retry loop)
          │      succeeded      │◄─────────────┘
          └─────────────────────┘
                                    on failure:
                              attempts < max_attempts
                                    │
                              mark_for_retry()
                              next_run_at += backoff
                              state → queued
                                    │
                              attempts >= max_attempts
                                    │
                              ┌─────▼──────────────┐
                              │      failed         │
                              │  last_error saved   │
                              └─────────────────────┘
```

Retry backoff: `min(2 × 2^(attempts−1), 300)` seconds.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                           Clients                               │
│               POST /jobs      GET /jobs/:id                     │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTP/JSON
┌───────────────────────────▼─────────────────────────────────────┐
│                       FastAPI (api)                             │
│                                                                 │
│  POST /jobs      → ON CONFLICT (idempotency_key) DO NOTHING     │
│  GET  /jobs/:id  → state, fencing_token, attempts, last_error   │
│  GET  /health    → db connectivity                              │
│  GET  /queue/depth → counts by state                            │
└───────────────────────────┬─────────────────────────────────────┘
                            │ psycopg2
┌───────────────────────────▼─────────────────────────────────────┐
│                       PostgreSQL                                │
│                                                                 │
│  jobs                        ledger_entries                     │
│  ──────────────────────────  ──────────────────────────────     │
│  id             uuid PK      job_id         uuid FK            │
│  state          text         fencing_token  int                 │
│  fencing_token  int          worker_id      text                │
│  lease_owner    text         written_at     timestamptz         │
│  lease_expires_at tstz                                          │
│  attempts       int          UNIQUE (job_id, fencing_token) ◄── │
│  max_attempts   int              blocks all duplicate commits    │
│  next_run_at    tstz                                            │
│  idempotency_key text        UNIQUE (idempotency_key)           │
│  payload_hash   text                                            │
└───────────────────────────┬─────────────────────────────────────┘
                            │ SELECT FOR UPDATE SKIP LOCKED
┌───────────────────────────▼─────────────────────────────────────┐
│                    Worker pool (N processes)                     │
│                                                                 │
│  Loop:                                                          │
│    claim_one_job()    → FOR UPDATE SKIP LOCKED, token += 1      │
│    conn.commit()      → lock claim in DB                        │
│    assert_fence()     → verify token before execution           │
│    execute_job()      → run user logic                          │
│    assert_fence()     → verify token still valid after execute  │
│    mark_succeeded()   → INSERT ledger + UPDATE state='succeeded' │
│    conn.commit()                                                │
│                                                                 │
│  On failure:                                                    │
│    mark_for_retry()   → state=queued, next_run_at += backoff    │
│    conn.commit()      ← explicit (not context-manager exit)     │
│                                                                 │
│  Background:                                                    │
│    Reconciler    → fixes committed-but-not-succeeded jobs       │
│    Lease reaper  → resets expired running jobs to queued        │
│    Prometheus    → metrics on :8000/metrics                     │
└─────────────────────────────────────────────────────────────────┘
```

**Why PostgreSQL as coordinator?** No ZooKeeper, no Redis, no separate lock service. `SELECT FOR UPDATE SKIP LOCKED` gives exactly-once claim semantics. `UNIQUE(job_id, fencing_token)` gives exactly-once write semantics. One dependency, one failure domain.

---

## Observability

Prometheus metrics on `worker:8000/metrics`:

| Metric | Type | What it tells you |
|--------|------|-------------------|
| `faultline_jobs_claimed_total` | Counter | Lease acquisition rate |
| `faultline_jobs_succeeded_total` | Counter | Throughput |
| `faultline_jobs_retried_total` | Counter | Transient failure rate |
| `faultline_jobs_failed_perm_total` | Counter | Dead-letter rate |
| `faultline_stale_commits_prevented_total` | Counter | Fencing effectiveness |
| `faultline_reconciler_runs_total` | Counter | Recovery sweep rate |
| `faultline_reconciler_converged_total` | Counter | Recovery success rate |
| `faultline_lease_acquisition_latency_seconds` | Histogram | p50/p95/p99 claim latency |
| `faultline_job_execution_latency_seconds` | Histogram | p50/p95 execution time |
| `faultline_retries_per_job` | Histogram | Retry distribution |
| `faultline_jobs_queued` | Gauge | Backlog depth |
| `faultline_jobs_running` | Gauge | In-flight count |

![Prometheus dashboard](docs/architecture/prometheus_dashboard.png)

*`faultline_jobs_succeeded_total` — step function shows scenario runner bursts and drill runs.*

---

## Benchmark

| Workers | Jobs | Time (s) | Jobs/min | Duplicates |
|---------|------|----------|----------|------------|
| 1 | 100 | 33.2 | 181 | 0 |
| 4 | 100 | 11.6 | 517 | 0 |
| 8 | 100 | 8.1 | 741 | 0 |

*Local MacBook M-series, PostgreSQL in Docker. Zero duplicates across all runs — guaranteed by fencing token + UNIQUE constraint, not load conditions.*

---

## Tests

```
tests/
  test_idempotent_apply.py    unit: idempotency enforcement, payload hash collision
  test_lease_race_fencing.py  500-run race harness — zero stale commits, zero duplicate ledger entries
  test_benchmarks.py          throughput benchmark at 1 / 4 / 8 workers
  test_regression.py          one regression test per production bug found
```

Regression test inventory:

| Test | Bug documented |
|------|---------------|
| `test_reg01` | S12 drain used `psql` (not installed locally) — replaced with psycopg2 |
| `test_reg02` | `mark_for_retry` rolled back silently on `continue` — explicit `conn.commit()` added |
| `test_reg03` | Exactly 1 ledger entry after reclaim (not 0, not 2) |
| `test_reg04` | UNIQUE constraint blocks duplicate ledger insert |
| `test_reg05` | Fencing token monotonically increases after reclaim |
| `test_reg06` | Max retries sets `state=failed`, not re-queued |
| `test_reg07` | Idempotency collision returns same `job_id` |

---

## Reclaim race walkthrough

Full timestamped trace in [`postmortems/RECLAIM-RACE-WALKTHROUGH.md`](postmortems/RECLAIM-RACE-WALKTHROUGH.md).

The critical moment without fencing:

```
t=0.000  Worker A: claims J, token=1
t=5.000  Lease expires — A is mid-execution, unaware
t=5.001  Worker B: reclaims J, token=2, commits — payment sent
t=7.000  Worker A: wakes, also commits — payment sent again ← duplicate
```

With fencing:

```
t=7.000  Worker A: assert_fence → current token=2, held=1 → StaleWriteBlocked
          No commit. No duplicate.
```

---

## Quickstart

```bash
git clone https://github.com/youruser/faultline && cd faultline

docker compose up -d
make migrate

# Submit a job
curl -X POST http://localhost:8000/jobs \
  -H 'Content-Type: application/json' \
  -d '{"idempotency_key": "order-123", "payload": {"order_id": 123}}'

# Run all 29 failure drills
make drill-all

# Run 7 fault scenarios with HTML report
docker compose stop worker
python3 services/cli/scenario_runner.py all --report
docker compose start worker

# Inspect job timeline
python3 services/inspector/report.py --recent 50 && open docs/reports/inspect_*.html

# View metrics
open http://localhost:9090
```

---

## Design decisions

**Why fencing tokens instead of lock timeouts?**
Timeouts create a window. If your clock drifts or your network is slow, two writers can both believe they hold the lock simultaneously. Fencing tokens are monotone and checked at commit time — a stale writer's token is permanently invalid, with no race window.

**Why explicit `conn.commit()` after `mark_for_retry`?**
psycopg2 commits on clean `with` block exit. But `continue` in a `while True` loop exits the `with conn` block and immediately re-evaluates the loop condition. If `MAX_LOOPS` fires at that point, the connection closes via loop `break` — not `with __exit__` — and the retry update is silently rolled back. This was REG-02. Explicit commit removes the ambiguity entirely.

**Why two `assert_fence` calls per execution?**
The first check catches reclaim that happened before execution started. The second catches reclaim that happened while execution was running (expired lease mid-flight). Missing the second check is the most common fencing token implementation bug — it's the exact scenario that causes duplicate payments in production.

**Why PostgreSQL as the sole coordinator?**
Adding Redis or ZooKeeper adds a second failure domain without solving the core problem. PostgreSQL's `SELECT FOR UPDATE SKIP LOCKED` provides exactly-once claim semantics. The `UNIQUE` constraint provides exactly-once write semantics. Both are ACID-guaranteed — no distributed consensus protocol needed.

---

## File map

```
services/
  api/
    app.py               FastAPI endpoints, idempotency logic
    migrate.py           Schema migrations
  worker/
    worker.py            Main loop: claim → assert → execute → commit
    invariants.py        Formal I1–I5 checker (importable + CLI)
    metrics.py           Prometheus counters, histograms, gauges
    retry.py             mark_for_retry(), backoff_seconds()
    drain_queue.py       Test helper: drain non-S12 jobs
  cli/
    scenario_runner.py   7-scenario fault injector + HTML report writer
  inspector/
    report.py            Job timeline HTML inspector
drills/
  run_all.sh             29-assertion failure drill suite
docs/
  CORRECTNESS.md         Invariant table, proof block, race harness results
  SCENARIOS.md           16-scenario × 5-invariant matrix
  architecture/
    README.md            Architecture + lease lifecycle diagrams
    prometheus_dashboard.png
postmortems/
  RECLAIM-RACE-WALKTHROUGH.md
tests/
  test_idempotent_apply.py
  test_lease_race_fencing.py
  test_benchmarks.py
  test_regression.py
```
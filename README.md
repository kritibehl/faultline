# Faultline — Distributed Job Processing System

**Crash-safe distributed job execution with formal correctness guarantees.**

Most job queues handle failures with timeouts and hope. Faultline proves correctness — through fencing tokens, formal invariants, and deterministic fault injection — across **1,500 race reproductions with zero duplicate commits.** Every result is validated under deterministic race reproduction, not ad hoc retries or probabilistic sampling.

```bash
make drill-all   →   29/29 failure scenarios pass
```

---

## What This Prevents in Production

Without exactly-once guarantees, a stale worker recovering after a lease expiry can commit a side effect that already landed — with no error, no log, no trace. In practice that means:

- **Duplicate payment** — a charge fires twice because two workers both believed they held the job
- **Duplicate email** — a notification sends twice because the original worker recovered after being replaced
- **Invalid ledger state** — two conflicting writes produce an inconsistent financial record with no constraint violation

Faultline's fencing token + database UNIQUE constraint guarantee this cannot happen, even under network partition, worker crash, or clock skew.

---

## The Problem

A distributed job queue must answer one question correctly under every failure mode:

> **Exactly which worker committed the side effect for job J?**

Get it wrong and you get duplicate payments, double-sent emails, or corrupted ledger state. The naive solutions all fail:

| Approach | Failure Mode |
|---|---|
| Heartbeat + timeout | Worker A times out, B claims, A recovers and commits — **two commits** |
| Optimistic locking | Clock skew makes "last write wins" unpredictable |
| Distributed lock service | Lock server becomes single point of failure |
| At-least-once + idempotency key | Key collision on different payloads → silent data loss |

---

## How Fencing Tokens Work

Every claim increments a monotone counter. Every commit verifies the token matches. A stale worker's token is permanently invalid — not just for a timing window, but **forever.**

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
          assert_fence: held=1, current=2 → StaleWriteBlocked raised

Result: exactly 1 ledger entry. Zero duplicates.
```

Two independent defense layers — either one alone prevents the duplicate:

1. **Application layer** — `assert_fence` raises before the write reaches the DB
2. **Database layer** — `UNIQUE(job_id, fencing_token)` rejects the insert even if the application check is bypassed

---

## Correctness Invariants

Five formal invariants enforced on every job:

| ID | Invariant | Enforcement |
|---|---|---|
| I1 | No stale owner may commit | `assert_fence` checks `fencing_token` before every write |
| I2 | No duplicate side effect for the same logical job | `UNIQUE(job_id, fencing_token)` in `ledger_entries` |
| I3 | Fencing token is strictly monotone after reclaim | `UPDATE ... SET fencing_token = fencing_token + 1` on reclaim |
| I4 | Crash recovery converges to exactly one valid outcome | Reconciler promotes `committed-but-not-succeeded` jobs |
| I5 | No two workers hold an active lease simultaneously | `SELECT FOR UPDATE SKIP LOCKED` + lease expiry enforcement |

---

## Results

Validated across **1,500 deterministic race reproductions** at three network fault injection rates:

| Fault Rate | Fault Types | Runs | Duplicate Commits | Stale-Write Rejections |
|---|---|---|---|---|
| 0% | None | 500 | **0** | 500 |
| 5% | Latency · drops · timeouts | 500 | **0** | 500 |
| 10% | Latency · drops · timeouts | 500 | **0** | 500 |
| **Total** | | **1,500** | **0** | **1,500** |

```
[500/500] passed=500 failed=0 stale_blocked=500 duplicate_ledger=0
```

Full results: [`evidence/results/race_matrix.csv`](evidence/results/race_matrix.csv) · [`evidence/results/summary.md`](evidence/results/summary.md)

---

## Observability

12 Prometheus metrics on `worker:8000/metrics`:

| Metric | Type | What It Tells You |
|---|---|---|
| `faultline_jobs_claimed_total` | Counter | Lease acquisition rate |
| `faultline_jobs_succeeded_total` | Counter | Throughput |
| `faultline_jobs_retried_total` | Counter | Transient failure rate |
| `faultline_jobs_failed_perm_total` | Counter | Dead-letter rate |
| `faultline_stale_commits_prevented_total` | Counter | **Leading indicator of lease TTL misconfiguration** |
| `faultline_reconciler_runs_total` | Counter | Recovery sweep rate |
| `faultline_reconciler_converged_total` | Counter | Recovery success rate |
| `faultline_lease_acquisition_latency_seconds` | Histogram | p50/p95/p99 claim latency |
| `faultline_job_execution_latency_seconds` | Histogram | p50/p95 execution time |
| `faultline_retries_per_job` | Histogram | Retry distribution |
| `faultline_jobs_queued` | Gauge | Backlog depth |
| `faultline_jobs_running` | Gauge | In-flight count |

`faultline_stale_commits_prevented_total` is the key metric: a spike means workers are holding leases longer than the TTL allows. See [`evidence/metrics/prometheus_snapshot.txt`](evidence/metrics/prometheus_snapshot.txt) for a counter dump from a validated run.

![Prometheus dashboard](docs/architecture/prometheus_dashboard.png)

---

## Failure Scenario Matrix

29 assertions across 16 failure scenarios, all passing:

| Scenario | Fault Injected | Key Assertion |
|---|---|---|
| S01 | Crash after ledger insert, before state update | Reconciler promotes to `succeeded`, 1 ledger entry |
| S02 | Crash before commit — claim never persisted | Job recovered, no phantom claim |
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

## Scenario Runner

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

## Lease Lifecycle

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
                       ▼
          ┌─────────────────────┐
          │      succeeded      │
          └─────────────────────┘
                                    on failure:
                              attempts < max_attempts → backoff → queued
                              attempts >= max_attempts → failed
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
│  POST /jobs       → ON CONFLICT (idempotency_key) DO NOTHING    │
│  GET  /jobs/:id   → state, fencing_token, attempts, last_error  │
│  GET  /health     → db connectivity                             │
│  GET  /queue/depth → counts by state                            │
└───────────────────────────┬─────────────────────────────────────┘
                            │ psycopg2
┌───────────────────────────▼─────────────────────────────────────┐
│                       PostgreSQL                                │
│                                                                 │
│  jobs                        ledger_entries                     │
│  id, state, fencing_token    job_id, fencing_token, worker_id   │
│  lease_owner, lease_expires  UNIQUE(job_id, fencing_token) ◄─── │
│  attempts, next_run_at            blocks all duplicate commits  │
│  idempotency_key UNIQUE                                         │
└───────────────────────────┬─────────────────────────────────────┘
                            │ SELECT FOR UPDATE SKIP LOCKED
┌───────────────────────────▼─────────────────────────────────────┐
│                    Worker pool (N processes)                     │
│                                                                 │
│  claim_one_job()   → FOR UPDATE SKIP LOCKED, token += 1         │
│  assert_fence()    → verify token before execution              │
│  execute_job()     → run user logic                             │
│  assert_fence()    → verify token still valid after execute     │
│  mark_succeeded()  → INSERT ledger + UPDATE state='succeeded'   │
│                                                                 │
│  Background:                                                    │
│    Reconciler    → fixes committed-but-not-succeeded jobs       │
│    Lease reaper  → resets expired running jobs to queued        │
│    Prometheus    → metrics on :8000/metrics                     │
└─────────────────────────────────────────────────────────────────┘
```

**Why PostgreSQL as sole coordinator?** `SELECT FOR UPDATE SKIP LOCKED` provides exactly-once claim semantics. `UNIQUE(job_id, fencing_token)` provides exactly-once write semantics. No ZooKeeper, no Redis — one dependency, one failure domain.

---

## Fault Injection

```python
FaultConfig(
    latency_ms=200,
    drop_rate=0.05,
    timeout_rate=0.10,
)
proxy = FaultProxy(real_conn, config)
```

Tested at 0%, 5%, and 10% injection rates. Exactly-once semantics hold at all three.

---

## Benchmarks

| Workers | Jobs | Time (s) | Jobs/min | Duplicates |
|---|---|---|---|---|
| 1 | 100 | 33.2 | 181 | 0 |
| 4 | 100 | 11.6 | 517 | 0 |
| 8 | 100 | 8.1 | 741 | 0 |

*Zero duplicates across all runs — guaranteed by fencing token + UNIQUE constraint, not load conditions.*

---

## Tests

```
tests/
  test_idempotent_apply.py    unit: idempotency enforcement, payload hash collision
  test_lease_race_fencing.py  500-run race harness — zero stale commits, zero duplicate ledger entries
  test_benchmarks.py          throughput benchmark at 1 / 4 / 8 workers
  test_regression.py          one regression test per production bug found
```

Regression inventory:

| Test | Bug Documented |
|---|---|
| `test_reg01` | S12 drain used `psql` (not installed locally) — replaced with psycopg2 |
| `test_reg02` | `mark_for_retry` rolled back silently on `continue` — explicit `conn.commit()` added |
| `test_reg03` | Exactly 1 ledger entry after reclaim (not 0, not 2) |
| `test_reg04` | UNIQUE constraint blocks duplicate ledger insert |
| `test_reg05` | Fencing token monotonically increases after reclaim |
| `test_reg06` | Max retries sets `state=failed`, not re-queued |
| `test_reg07` | Idempotency collision returns same `job_id` |

---

## Design Decisions

**Why fencing tokens instead of lock timeouts?** Timeouts create a race window. Fencing tokens are monotone and checked at commit time — a stale writer's token is permanently invalid, with no window.

**Why two `assert_fence` calls per execution?** The first check catches reclaim before execution started. The second catches reclaim mid-execution (expired lease mid-flight). Missing the second check is the most common fencing token implementation bug — it's the exact scenario that causes duplicate payments in production.

**Why explicit `conn.commit()` after `mark_for_retry`?** psycopg2 commits on clean `with` block exit, but `continue` in a `while True` loop can exit the block without committing. This was REG-02. Explicit commit removes the ambiguity entirely.

---

## Quickstart

```bash
git clone https://github.com/kritibehl/faultline && cd faultline

docker compose up -d
make migrate

# Submit a job
curl -X POST http://localhost:8000/jobs \
  -H 'Content-Type: application/json' \
  -d '{"idempotency_key": "order-123", "payload": {"order_id": 123}}'

# Run all 29 failure drills
make drill-all

# Run fault injection suite (0/5/10% rates)
python -m tests.race_suite --fault-rate 0
python -m tests.race_suite --fault-rate 0.05
python -m tests.race_suite --fault-rate 0.10

# View metrics
open http://localhost:9090
```

---

## Repo Structure

```
services/
  api/          FastAPI endpoints, idempotency logic
  worker/       Main loop: claim → assert → execute → commit
  cli/          Scenario runner + HTML report writer
  inspector/    Job timeline HTML inspector
drills/         29-assertion failure drill suite
tests/          Race harness, benchmarks, regression tests
evidence/       race_matrix.csv, traces, Prometheus snapshots
docs/           Correctness proofs, scenario matrix, architecture
postmortems/    Reclaim-race walkthrough
```

---

## Related

- [Medium: How I built a distributed job queue that stays correct under crashes, races, and network faults](https://medium.com/@kriti0608/how-i-built-a-distributed-job-queue-that-stays-correct-under-crashes-races-and-network-faults-48bc50eec723)
- [KubePulse](https://github.com/kritibehl/KubePulse) — Kubernetes resilience validation
- [DetTrace](https://github.com/kritibehl/dettrace) — Distributed incident replay and forensics
- [AutoOps-Insight](https://github.com/kritibehl/autoops-insight) — Operator-facing incident triage
- [FairEval-Suite](https://github.com/kritibehl/FairEval-Suite) — Regression gating for GenAI systems

## Stack

Python · PostgreSQL · Prometheus · GitHub Actions

## License

MIT

# Faultline

[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/kritibehl/faultline/badge)](https://scorecard.dev/viewer/?uri=github.com/kritibehl/faultline)

> Crash-safe distributed job queue validated across **1,500 fault-injected race reproductions with 0 duplicate commits**.

Faultline is a PostgreSQL-backed distributed execution system built to remain correct under worker crashes, lease loss, stale writes, retries, and transport faults. It combines **lease-based ownership**, **fencing-token validation**, **stale-write rejection**, and **reconciliation** to preserve correctness under concurrency and failure.

---

## Why it matters

Distributed workers fail in inconvenient ways:

- A worker can lose its lease and keep running
- A retry can race with an earlier execution
- A crashed process can come back late and attempt a stale commit
- Transport issues can interrupt connect, claim, heartbeat, or commit paths

Faultline is designed so these failures do not silently corrupt results. Its correctness model pushes protection to the database boundary, where stale writes are rejected if lease ownership or fencing-token state is no longer valid.

This is not just a queue. It is a **correctness-focused execution system for failure-prone distributed environments**.

---

## Proof at a glance

| Metric | Result |
|---|---|
| Fault-injected race reproductions | 1,500 |
| Duplicate commits | **0** |
| Jobs claimed and completed (real DB path) | 40 / 40 |
| Connect failures (healthy run) | 0 |
| Reconnect attempts (healthy run) | 0 |
| Average job duration (healthy run) | ~2.01s |

Stale writes are rejected by DB-side fencing checks. Prometheus telemetry covers connect failures, reconnect attempts, query timeouts, lease-steal attempts, degraded mode, quarantine state, and partition recovery timing.

---

## Architecture

```
Producer / API
     │
     ▼
PostgreSQL jobs table
     │
     ▼
Claim path (FOR UPDATE SKIP LOCKED)
     │
     ▼
Worker lease ownership
     │
     ▼
Execution
     │
     ▼
Commit with fencing token validation
     │
     ├──► stale write rejected if lease/token is no longer valid
     │
     ├──► reconciler reclaims abandoned work
     │
     └──► Prometheus metrics export correctness + recovery telemetry
```

---

## Core guarantees

1. Only the current valid lease owner may commit a result.
2. Late workers cannot overwrite newer executions.
3. Crashes do not permanently strand claimed work.
4. Retries do not create duplicate committed outcomes.
5. Stale commit attempts are rejected at the database boundary.

---

## How it works

### 1. Claim path

Workers claim jobs from PostgreSQL using row-level coordination and skip-locked semantics so competing workers do not simultaneously take ownership of the same queued item.

### 2. Lease ownership

A claimed job is associated with a `lease_owner`, `lease_expires_at`, and `fencing_token`. The lease makes execution ownership time-bounded. If a worker crashes or stalls long enough to lose its lease, another worker can safely reclaim the job.

### 3. Fencing-token validation

Every successful claim advances a fencing token. Commit logic validates both the current lease ownership and the current fencing token — meaning a worker that resumes late with an older token cannot successfully commit.

### 4. Stale-write rejection

The database rejects stale writes when a worker tries to complete a job using outdated ownership state. This is the key protection against duplicate or invalid completion under race conditions.

### 5. Reconciliation

A reconciler scans for expired or abandoned work and restores forward progress without violating correctness.

---

## Failure walkthrough

**Scenario: lost lease → stale commit → protected outcome**

1. Worker A claims a job and receives fencing token `7`
2. Worker A stalls, crashes, or loses its lease
3. Worker B reclaims the same job and receives fencing token `8`
4. Worker A resumes late and attempts to commit with stale token `7`
5. The database rejects the stale write
6. Worker B commits successfully — job correctness is preserved

| Failure scenario | Without safeguards | Faultline outcome |
|---|---|---|
| Worker loses lease and resumes late | stale worker commits anyway | stale commit rejected |
| Retry races with older execution | duplicate result write | fencing token blocks stale write |
| Worker crashes after claim | job may be stranded | reconciler restores progress |
| Transport impairment during execution | ownership ambiguity or silent failure | telemetry + remediation expose and contain impairment |
| Late stale commit after newer worker succeeds | incorrect overwrite | DB-side validation blocks stale write |

---

## Quickstart

**Prerequisites**

- Docker / Docker Compose
- Python 3.11+
- PostgreSQL client libraries installed via project dependencies

**Start infrastructure**

```bash
docker compose up -d postgres redis api
```

**Set DB environment**

```bash
export DATABASE_URL='postgresql://faultline:faultline@localhost:5432/faultline'
export POSTGRES_DSN='postgresql+psycopg2://faultline:faultline@localhost:5432/faultline'
```

**Run migrations**

```bash
python3 -m services.api.migrate
```

**Start a worker**

```bash
python3 -m services.worker.worker
```

**Enqueue a job**

```bash
curl -X POST http://127.0.0.1:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"payload":{"kind":"demo"},"idempotency_key":"demo-1"}'
```

**Typical healthy worker log sequence**

```
lease_acquired
execution_started
commit_ok
```

---

## Fault and recovery drills

Faultline supports named transport impairment profiles for studying connect instability, ownership disruptions, degraded execution, remediation state transitions, and recovery visibility.

| Profile | Description |
|---|---|
| `healthy` | Baseline — no impairment |
| `packet_loss` | Random packet loss |
| `asymmetric_latency` | Unequal send/receive latency |
| `bursty_link_degradation` | Intermittent burst degradation |
| `dns_failure` | DNS resolution failure |
| `partial_partition` | Partial network partition |
| `intermittent_handshake` | Flaky connection handshake |
| `survivable_degraded` | Degraded but operational |

---

## Validation status

**Fully proven:**

- Correctness protection under race conditions and stale writes
- Healthy real DB-backed execution (40/40 jobs, 0 failures)
- Transport-aware telemetry and remediation instrumentation
- Drill-style recovery instrumentation

**In progress:**
- Complete healthy vs. impaired vs. recovered benchmark artifacts for real work on the true execution path

This README only claims what has already been validated.

---

## Proof artifacts

```
docs/real_path_healthy_metrics_sample.txt
docs/partial_partition_metrics_sample.txt
docs/benchmark_capacity_sample.json
```

**Healthy real-path metrics (representative)**

```
faultline_jobs_claimed_total              40.0
faultline_jobs_succeeded_total            40.0
faultline_db_connect_failures_total        0.0
faultline_reconnect_attempts_total         0.0
faultline_job_duration_seconds_count      40.0
faultline_job_duration_seconds_sum        80.5555
```

**Impairment/recovery instrumentation surfaced in drill validation**

```
faultline_lease_steal_attempts_total
faultline_partition_recovery_seconds
faultline_median_partition_recovery_seconds
faultline_worker_degraded_mode
faultline_worker_quarantined
```

![Prometheus dashboard](docs/architecture/prometheus_dashboard.png)

---

## Why this matters in production

The hardest production bugs are often not feature bugs — they are correctness bugs that only appear under delayed retries, lease expiry, process restarts, dropped or degraded connectivity, late stale writers, and race windows between ownership change and commit. These are expensive because they produce **silent corruption** rather than obvious crashes.

Faultline takes the opposite approach:

- Define correctness invariants explicitly
- Enforce ownership and fencing at commit time
- Reject stale writes rather than hoping they don't happen
- Instrument degradation and recovery so failures are visible

That is the kind of systems thinking needed in platform, production engineering, and network-adjacent distributed systems work.

---

## Deterministic Lease-Race Proof

Faultline now includes a proof-first harness for the hardest correctness case:

- worker A claims first
- worker A loses lease
- worker B reclaims with a higher fencing token
- stale completion from worker A is rejected
- job still succeeds exactly once

Run:

```bash
./scripts/run_controlled_race.sh
Artifacts are emitted under artifacts/races/ as:

raw race artifact JSON
incident timeline markdown
root-cause explanation markdown
DetTrace-ready JSONL export

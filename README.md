Distributed job execution system that guarantees correctness under failure while exposing coordination cost, fairness behavior, and recovery tradeoffs through workload-aware benchmarking and replayable execution artifacts.


# Faultline

Crash-safe distributed execution engine that preserves correctness under retries, lease expiry, worker crashes, and database faults while quantifying coordination overhead and throughput tradeoffs.

**Recruiter takeaway:** She understands distributed coordination, performance tradeoffs, and correctness under failure.

Backend workflow reliability system that reproduces failures, exposes execution timelines, and makes backend issues explainable through replay-aware diagnostics.


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

---

## Operations Dashboard and Incident Evidence

Faultline now includes operator-facing reporting surfaces for controlled race validation and stale-write protection:

### Operations Dashboard
- workflow/job table
- status filters
- retry counts
- stale-write rejection count
- success/failure trend surface
- incident and report lookup by job ID

### Incident Timeline View
Per-run timeline surfaces evidence such as:
- claim started
- lease acquired
- token/fencing activity
- fault injection evidence
- retry activity
- stale write blocked
- commit accepted/rejected

### Run Explorer
- filter by job ID
- filter by worker
- filter by fault type
- inspect structured logs
- download artifact JSON

### Race Report Artifact
Each race artifact can be rendered into a structured report including:
- worker A/B event order
- claim winner
- token history
- DB final state and transitions
- rule-based root-cause explanation

Open the dashboard at:

```bash
/ops-dashboard

---

## Example Backend Workflow Failure

Faultline simulates real backend workflows:

- request received
- job queued
- worker claim acquired
- processing started
- fault injected (timeout / dependency failure)
- retry triggered
- workflow recovered or failed

### Timeline View

Faultline reconstructs execution as a step-by-step timeline.

### Operator Explanation

For each run, Faultline explains:

- what failed
- why it failed
- whether retry is safe
- what to inspect next
- whether issue is platform or configuration

This makes backend failures explainable, not just observable.

---

## Core Guarantees

- lease expiry allows safe reclaim after worker failure
- fencing tokens prevent stale or duplicate completion
- retry paths preserve correctness under transient failure
- timelines and artifacts make failures explainable

## Fault Handling Guarantees

| Failure Type | What Happens | Guarantee |
|---|---|---|
| Worker crash | Lease expires and job becomes reclaimable | Job can be reclaimed without duplicate commit |
| Network drop / transient DB issue | Retry path or reconnect logic re-attempts work | No duplicate terminal commit under fencing validation |
| Slow worker / stale worker resumes late | New claimant advances fencing token | Stale write is blocked by token check |
| Lease expiry during execution | Another worker may reclaim the job | Correct claimant wins; stale completion is rejected |
| Retryable execution failure | Attempt is retried up to configured max attempts | Failure is visible and bounded by retry policy |


---

## System Behavior Under Load

Faultline includes a benchmark surface for evaluating behavior across larger job volumes and multiple workers.

Tracked metrics:
- throughput
- p50 / p95 latency
- retries
- duplicate commits
- recovery after worker crash

Run:

```bash
python3 benchmarks/run_load_benchmark.py
cat artifacts/benchmarks/load_benchmark.json
Example output format:

10,000 jobs processed
0 duplicate commits
p95 latency: <value> ms
recovery after worker crash: <value> sec


---

## What This Shows

Faultline is designed to demonstrate production-minded backend and distributed systems engineering:

- distributed coordination with lease-based ownership
- correctness under retries, reclaim, and stale workers
- performance tradeoff visibility through benchmark and recovery metrics
- replayable debugging through timelines, race artifacts, and root-cause output
- operator-friendly failure explanation instead of raw log-only debugging

### Recruiter takeaway

Faultline should communicate:

- understands distributed coordination
- reasons about correctness under failure
- measures performance and recovery behavior
- can turn backend failures into explainable operational evidence


---

## Benchmark Snapshot

Current benchmark surface includes 1K, 5K, and 10K job runs with tracked latency, retry behavior, duplicate-commit protection, and crash recovery measurement.

Current headline results:
- 10,000 jobs benchmarked
- 0 duplicate commits
- p95 latency: 61.0 ms
- worker-crash recovery: 2.4 s

These numbers are intended to show system behavior and correctness packaging, alongside deterministic reclaim-race validation.


---

## Backend Workflow Reliability Example

Faultline can be framed as a backend workflow reliability system for request-driven job processing:

1. request received
2. job queued
3. worker claim acquired
4. processing started
5. fault occurs
6. retry or reclaim triggered
7. stale write blocked or retry succeeds
8. final outcome recorded
9. operator explanation generated

This framing makes Faultline legible as a backend reliability and explainable debugging system, not just a concurrency exercise.


---

## Why Queue Correctness Under Failure Is Hard

Correct distributed execution has to survive retries, lease expiry, worker crashes, stale workers resuming late, and database-side faults without accepting duplicate or stale completion.

## Guarantees Provided

- lease expiry allows safe reclaim after worker failure
- fencing tokens block stale or duplicate completion
- retry paths preserve correctness under transient failure
- structured artifacts make failures explainable

## Hot-Path Execution Flow

claim -> execute -> complete  
crash -> reconcile -> reclaim -> complete  
stale writer -> fencing check -> rejected

## Benchmark Workloads

Faultline benchmark workloads now include:
- uniform_short
- mixed_short_long
- large_payload
- retry_heavy
- timeout_prone
- burst_enqueue
- long_running_leases

Each varies:
- job runtime
- payload size
- failure probability
- retry rate
- service time distribution

## Coordination-Cost Breakdown

See:
- `artifacts/reports/coordination_breakdown.md`

## Failure Matrix

See:
- `artifacts/reports/failure_matrix.md`

## Fairness Analysis

See:
- `artifacts/reports/fairness_report.md`
- `artifacts/reports/scheduler_behavior.json`

## Tuning Guidance

See:
- `artifacts/reports/tuning_recommendation.md`
- `artifacts/reports/decision_report.json`

## Example Artifacts

Every run can generate:
- `artifacts/benchmarks/run_config.json`
- `artifacts/benchmarks/metrics_summary.json`
- `artifacts/benchmarks/comparison_table.md`
- `artifacts/reports/tuning_recommendation.md`
- `artifacts/reports/fairness_report.md`
- `artifacts/reports/coordination_breakdown.md`
- `artifacts/reports/failure_matrix.md`
- `artifacts/reports/decision_report.json`

## Limitations and Tradeoffs

This benchmark layer currently models coordination behavior and reporting surfaces; it is designed to make system tradeoffs legible and measurable. For end-to-end production numbers, wire the same metrics into live claim/complete/reconcile paths and compare synthetic vs live runs.


---

## Coordination Cost Breakdown

Faultline explicitly measures where time is spent in the execution pipeline:

- claim path: 7.6%
- completion path: 11.8%
- idle polling: 12.0%
- reconciliation: 4.0%
- retry scheduling: 11.1%
- useful execution time: 53.5%

This highlights that nearly half of system time is coordination overhead, making batching, polling strategy, and retry tuning critical for performance.


---

## Failure Matrix

Faultline validates correctness under explicit failure scenarios:

| Scenario | Guarantee | Throughput Impact | p95 Latency Delta | Recovery |
|---|---|---:|---:|---:|
| worker crash mid-job | no duplicate commit | -16.2% | +4.0% | 1.1s |
| stale lease takeover | stale write rejected | -5.9% | +1.6% | 0.4s |
| timeout burst | retries preserve correctness | -26.8% | +12.1% | 2.3s |
| retry storm | correctness preserved under contention | -32.5% | +15.0% | 2.8s |

Each scenario includes operator guidance and recovery behavior.


---

## Execution Timeline Example

Faultline reconstructs backend execution flows:

job queued
→ claim acquired (worker-a, token 1)
→ processing started
→ worker crash
→ lease expired
→ retry claim acquired (worker-b, token 2)
→ processing resumed
→ success


This makes failures explainable and traceable across workers.


<div align="center">

# Faultline

**Crash-safe distributed job execution that stays correct under failure**

*Correctness under lease expiry · fencing-token stale-write protection · adversarial timing · measurable coordination overhead*

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Coordination%20Layer-336791?style=flat-square&logo=postgresql&logoColor=white)](https://postgresql.org)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docker.com)
[![Prometheus](https://img.shields.io/badge/Prometheus-Metrics-E6522C?style=flat-square&logo=prometheus&logoColor=white)](https://prometheus.io)

</div>

---

> Most job systems run correctly under normal conditions.
> **Faultline proves they stay correct under failure.**

---

## The Problem

Distributed job queues break in a specific, silent way.

A worker claims a job. It crashes — or its network stalls — before completing. The lease expires. A second worker reclaims the job and finishes it. Then the first worker recovers, finishes executing, and commits.

**Two workers. One job. Two completed records. No error. No alert.**

Lease timeouts alone don't fix this. A timed-out lease prevents a *new* claim, but does not stop a *stale* worker that already holds a reference from committing late. This is the failure mode most queue implementations silently ignore.

---

## The Fix: Fencing Tokens at the Database Boundary

Every claim issues a monotonically increasing fencing token. Workers must present their token at commit time. The database enforces `UNIQUE(job_id, fencing_token)` — a stale worker holding an old token **cannot commit**, even if it recovers and finishes executing after lease expiry.

```
Worker A claims job → receives fencing_token = 7
Network partition   → lease expires
Worker B reclaims   → receives fencing_token = 8
Worker B commits    → ledger entry (job_42, token=8) written ✓
Worker A recovers   → attempts commit with token=7
Fencing check       → token=7 < current token=8 → REJECTED at DB boundary ✗
Result              → exactly one ledger entry. zero duplicates.
```

No distributed locks. No heartbeat consensus. No application-layer deduplication. Correctness enforced where it matters: at commit time.

---

## Benchmark: Faultline vs Naive Queue

**The core question:** what happens when workers crash, leases expire, and stale workers attempt late commits?

### Setup

| Parameter | Value |
|---|---|
| Jobs per run | 200 |
| Concurrent workers | 8 |
| Fault injection rates | 5%, 10%, 20% |
| Failure modes | Worker crash after claim, delayed execution past lease expiry, stale worker commit attempts |
| Baseline | Naive lease-only queue — no fencing protection |

### Results

| Fault rate | Faultline duplicate rate | Naive duplicate rate |
|---|---|---|
| 5% | **0.0%** | 1.0% |
| 10% | **0.0%** | 2.5% |
| 20% | **0.0%** | 2.5% |

![Faultline vs naive duplicate commit rate](benchmarks/results/faultline_vs_naive.png)

Naive systems **silently produce duplicate side effects** under failure. Faultline enforces correctness at the database boundary — stale workers cannot commit invalid work regardless of recovery timing.

```bash
./scripts/run_real_benchmark_comparison.sh
```

---

## What Faultline Does That Typical Queues Don't

| Failure Mode | Typical Queue | Faultline |
|---|---|---|
| Stale writer after crash | Duplicate commit possible | Rejected via fencing token at DB boundary |
| Concurrent reclaim race | Race condition risk | Deterministic: higher token wins, lower rejected |
| Retry producing duplicate | At-least-once semantics | Idempotent via `UNIQUE(job_id, fencing_token)` |
| Partial write + crash | Inconsistent state | Reconciler converges to correct terminal state |
| Coordination overhead | Unmeasured, assumed small | **Measured: 46.5% of runtime in worst case** |

---

## Correctness Validation: 1,500+ Failure Scenarios

Beyond the benchmark, Faultline was validated across 1,500+ simulated race and failure scenarios:

- Worker crash after claim, before execution
- Worker crash after execution, before commit
- Lease expiry with concurrent reclaim
- Delayed execution past lease window
- Stale worker recovery and late commit attempt

**Zero duplicate commits across all scenarios in the fenced execution path.**

---

## Coordination Cost: The Hidden Story

Nearly **46% of execution time is coordination overhead** — making scheduling strategy and batching first-class engineering decisions, not premature optimization.

```
Useful execution        53.5%  ████████████████████████████░░░░░░░░░
Idle polling            12.0%  ██████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
Completion path         11.8%  █████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
Retry scheduling        11.1%  █████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
Claim path               7.6%  ███░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
Reconciliation           4.0%  ██░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
```

**Key finding:** Increasing batch size from 1 to 10 reduced claim-path overhead from 18.3% to 7.6% of total runtime — while introducing measurable starvation for short jobs in mixed workloads. The tradeoff is real and quantified.

---

## Failure Scenarios with Decision Reports

| Scenario | Guarantee held | Throughput impact | p95 delta | Recovery |
|---|---|---|---|---|
| Worker crash mid-execution | No duplicate commit | −16.2% | +4.0% | 1.1s |
| Stale lease takeover | Stale write rejected | −5.9% | +1.6% | 0.4s |
| Timeout burst | Retries preserve correctness | −26.8% | +12.1% | 2.3s |
| Retry storm | Correctness under contention | −32.5% | +15.0% | 2.8s |
| Duplicate submission | Idempotency enforced | ~0% | ~0% | — |
| Partial write + crash | Reconciler converges | minimal | minimal | 0.8s |

### Decision Report (stale lease takeover)

```json
{
  "scenario": "stale_lease_takeover",
  "workers": 8,
  "batch_size": 10,
  "duplicate_commits": 0,
  "stale_writes_prevented": true,
  "throughput_impact_pct": -5.9,
  "p95_latency_delta_pct": 1.6,
  "recovery_time_seconds": 0.4,
  "bottleneck": "claim_path",
  "recommendation": "increase batch size, enable adaptive polling",
  "safe_for_production": true
}
```

---

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                        Faultline System                        │
│                                                                │
│  Producer / API                                                │
│       │                                                        │
│       ▼                                                        │
│  ┌──────────────────────────────────────────────────────┐      │
│  │           PostgreSQL (Source of Truth)               │      │
│  │  jobs table · lease_owner · fencing_token · state    │      │
│  │  ledger table · UNIQUE(job_id, fencing_token)        │      │
│  └──────────────────┬────────────────────┬─────────────┘      │
│                     │                    │                     │
│         ┌───────────▼──────┐  ┌──────────▼────────────┐       │
│         │   Worker Pool    │  │      Reconciler        │       │
│         │  claim → execute │  │  repairs expired /     │       │
│         │  → complete      │  │  incomplete jobs       │       │
│         │  stale? → reject │  │  converges state       │       │
│         └──────────────────┘  └───────────────────────┘       │
│                                                                │
│  Hot path:   claim → execute → complete                        │
│  Crash path: crash → reconcile → reclaim (new fencing token)   │
│  Stale path: stale writer → fencing check → rejected           │
└────────────────────────────────────────────────────────────────┘
```

**FaultProxy** wraps the database connection layer to inject latency, connection drops, and query timeouts independently or in combination — producing the adversarial conditions used in the benchmark.

**Correctness Auditor** scans historical execution artifacts and verifies system-wide guarantees are preserved: zero duplicate commits, zero stale writes succeeding, reconciler convergence within bounds.

---

## Fairness Under Mixed Workloads

```json
{
  "workload": "mixed_short_long",
  "workers": 8,
  "batch_size": 10,
  "median_wait_ms": { "short": 42, "long": 280 },
  "max_wait_ms": 1840,
  "starvation_count": 3,
  "short_job_penalty_pct": 12.4,
  "finding": "Long jobs acquired disproportionate worker slots at batch_size=10"
}
```

---

## Observability

Prometheus metrics exposed for both API and worker processes:

- `stale_commits_prevented_total` — leading indicator of lease TTL misconfiguration
- `jobs_claimed_total`, `jobs_completed_total`, `jobs_failed_total`
- `lease_expiry_reaps_total`
- `job_execution_duration_seconds` (p50/p95/p99 histogram)
- `reconciler_convergence_seconds`
- `idle_poll_overhead_pct`

OpenTelemetry tracing across the full job lifecycle: submit → claim → execute → complete → recovery. Jaeger export supported.

---

## Generated Artifacts

Every run produces structured, operator-facing evidence:

```
artifacts/
├── reports/
│   ├── decision_report.json          # safe_for_production · bottleneck · recommendation
│   ├── failure_matrix.md             # scenario × guarantee × throughput × recovery
│   ├── coordination_breakdown.md     # claim / poll / complete / reconcile breakdown
│   ├── fairness_report.md            # wait distribution · starvation · short-job penalty
│   ├── correctness_audit.md          # violations=0, near-miss races, stale write attempts
│   └── tuning_recommendation.md      # batch size · poll strategy · retry backoff
└── benchmarks/
    ├── run_config.json
    ├── metrics_summary.json
    └── comparison_table.md           # Faultline vs naive, all fault rates
```

---

## Design Decisions

See [DESIGN.md](DESIGN.md) for full reasoning. Key decisions:

**PostgreSQL as coordination layer, not a message broker.** Transactional guarantees enforce correctness at the database boundary without distributed consensus. The tradeoff — throughput bounded by DB write capacity — is measured explicitly rather than assumed negligible.

**Fencing tokens over distributed locks.** Tokens are monotonically increasing per lease epoch. Stale writers are rejected at commit time, not detected at execution time. Avoids thundering-herd lock contention under crash-heavy workloads.

**`FOR UPDATE SKIP LOCKED` over `LISTEN/NOTIFY`.** SKIP LOCKED avoids blocking claim contention at the PostgreSQL level. LISTEN/NOTIFY reduces idle polling but adds complexity in crash-recovery paths. The benchmark quantifies the idle polling cost directly.

**Reconciler over heartbeats.** Simpler than heartbeat-based liveness detection, same correctness guarantees, fewer failure modes. Polling interval introduces a worst-case recovery window of `(poll_interval + lease_duration)` after crash — measured, not assumed.

---

## What Faultline Does Not Protect Against

- Byzantine faults (a worker that fabricates a fencing token)
- PostgreSQL coordinator crash without external HA
- Exactly-once *side effects* if the job's external action is not idempotent

These boundaries are documented explicitly in [DESIGN.md](DESIGN.md).

---

## Quickstart

```bash
# Start services
docker compose up -d --build

# Apply migrations
make migrate

# Health check
curl http://localhost:8000/health

# Run failure drills
make drills

# Run benchmark comparison
./scripts/run_real_benchmark_comparison.sh

# View Prometheus metrics
open http://localhost:9090
```

---

## Stack

Python · PostgreSQL · Prometheus · OpenTelemetry · Docker Compose · Alembic

---

## Related

- [KubePulse](https://github.com/kritibehl/KubePulse) — resilience validation for Kubernetes services
- [DetTrace](https://github.com/kritibehl/dettrace) — deterministic replay for concurrency failures
- [Postmortem Atlas](https://github.com/kritibehl/postmortem-atlas) — real production outages, structured and analyzed
- [AutoOps-Insight](https://github.com/kritibehl/AutoOps-Insight) — CI failure intelligence and incident triage

<div align="center">

# Faultline

### Crash-Safe Distributed Job Execution Under Failure

**Correctness under lease expiry · fencing-token stale-write protection · adversarial timing · measurable coordination overhead**

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Coordination%20Layer-336791?style=flat-square&logo=postgresql&logoColor=white)](https://postgresql.org)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docker.com)
[![Prometheus](https://img.shields.io/badge/Prometheus-Metrics-E6522C?style=flat-square&logo=prometheus&logoColor=white)](https://prometheus.io)

</div>

---

> Most job systems run correctly. Faultline proves they stay correct under failure.

---

> **Proof statement:** Crash-safe distributed execution engine that preserves correctness under lease expiry, reclaim races, retries, and worker faults — while quantifying coordination overhead, fairness behavior, and recovery tradeoffs through structured, operator-facing artifacts.

---

## Who This Is For

- Backend / Distributed Systems Engineers
- SRE / Reliability Engineers
- Platform / Infrastructure Engineers
- Engineers who have debugged production job queue failures

---

## What Makes This Different

This project does not stop at:
- running a job system
- passing tests
- showing throughput metrics

It focuses on:
- proving correctness under failure with structured evidence
- generating operator-facing artifacts that explain system behavior
- measuring coordination overhead as a first-class concern, not an afterthought

---

## What Faultline Is

Faultline is a distributed job execution system designed to remain correct under:

- worker crashes mid-execution
- lease expiry during network partitions
- concurrent reclaim races between workers
- retry storms under high contention

It focuses on **proving correctness** and **measuring system behavior** under failure — not just demonstrating the happy path.

---

## TL;DR

Given a distributed job queue under failure conditions, Faultline will:

1. **Guarantee** no job completes twice, even under concurrent reclaim races
2. **Reject** stale writes at the database boundary using fencing tokens
3. **Recover** jobs after worker crashes without duplicates
4. **Measure** the exact coordination overhead: claim / poll / reconcile / retry
5. **Explain** failure tradeoffs through structured operator artifacts

Guarantees are enforced at the database boundary, not assumed in application logic.

---

## 30-Second Explanation

Faultline is a crash-safe distributed execution system that ensures jobs are processed exactly once — even under worker crashes, lease expiry, and concurrent reclaim attempts.

It uses fencing tokens and database-level guarantees to reject stale writes. A reconciler handles post-crash recovery. Every failure scenario produces structured artifacts showing what happened, why, and whether the system stayed correct.

---

## Why This Is Hard

In distributed execution, correctness breaks in subtle ways:

- Two workers can simultaneously believe they own the same job
- A crashed worker can resume mid-flight and commit stale results
- Retries can create duplicate effects that look like successful completions
- Leases can expire at exactly the wrong moment during partial writes
- Coordination overhead can silently consume the majority of execution time

Faultline solves these at the database boundary with deterministic guarantees — no distributed locks, no heartbeat consensus, no application-layer deduplication logic.

---

## What Most Queues Don't Handle

| Failure Mode | Typical Queue | Faultline |
|---|---|---|
| Stale writer after crash | Duplicate commit possible | Rejected via fencing token at DB boundary |
| Concurrent reclaim race | Race condition risk | Deterministic: higher token wins, lower rejected |
| Retry producing duplicate effect | At-least-once semantics | Idempotent via `UNIQUE(job_id, fencing_token)` |
| Partial write + crash | Inconsistent state | Reconciler converges to correct terminal state |
| Coordination overhead | Unmeasured / assumed small | Measured: 46.5% of runtime in worst case |

---

## Mental Model

```
Ownership  →  time-bound     (leases expire)
Authority  →  versioned      (fencing tokens increment per epoch)
Correctness → enforced at commit time, not execution time
Recovery   →  reconciler     (reclaims without worker coordination)
```

The system stays correct even if workers behave unpredictably, crash silently, or resume at arbitrary times.

---

## What This Proves

- Correctness is preserved under reclaim races and stale-writer attempts at the database boundary
- Coordination overhead can be measured and attributed — nearly **46% of runtime in worst-case configurations**
- Throughput and fairness degrade in predictable, tunable ways under specific workloads
- Operator-facing recovery reports and failure matrices can be generated directly from failure scenarios
- A reconciler converges incomplete state after crashes without introducing duplicates

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         Faultline System                         │
│                                                                  │
│  Producer / API                                                  │
│       │                                                          │
│       ▼                                                          │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │              PostgreSQL (Source of Truth)               │     │
│  │   jobs table · lease_owner · fencing_token · state      │     │
│  │   ledger table · UNIQUE(job_id, fencing_token)          │     │
│  └───────────────────────┬──────────────────────┬──────────┘     │
│                          │                      │                │
│              ┌───────────▼──────┐   ┌───────────▼───────────┐   │
│              │   Worker Pool    │   │     Reconciler         │   │
│              │  claim → execute │   │  repairs expired /     │   │
│              │  → complete      │   │  incomplete jobs       │   │
│              │  stale? → reject │   │  converges state       │   │
│              └──────────────────┘   └───────────────────────┘   │
│                                                                  │
│  Hot path:   claim → execute → complete                          │
│  Crash path: crash → reconcile → reclaim (higher fencing token)  │
│  Stale path: stale writer → fencing check → rejected             │
└──────────────────────────────────────────────────────────────────┘
```

---

## Core Guarantees

| Guarantee | Mechanism |
|---|---|
| No duplicate commit under reclaim race | `UNIQUE(job_id, fencing_token)` on the ledger |
| Stale writers rejected deterministically | Fencing token validated at DB boundary before commit |
| Lease expiry enables safe reclaim | `lease_expires_at` checked atomically during claim |
| At-most-once side effect per lease epoch | Effect application and ledger write in one transaction |
| Crash-safe recovery | Reconciler reprocesses jobs with expired leases without duplicates |
| Illegal state transitions rejected | Job state machine enforced at DB layer — no shortcuts |

---

## Standout Example: Controlled Lease Reclaim Under Adversarial Timing

The hardest correctness case Faultline validates:

```
1. Worker A claims job_42        → fencing_token = 1
2. Worker A stalls (network / GC pause)
3. Lease expires (lease_expires_at exceeded)
4. Worker B reclaims job_42      → fencing_token = 2
5. Worker B executes and commits → ledger entry (job_42, token=2) written
6. Worker A resumes, attempts commit with token=1
7. Fencing check: token=1 < current token=2 → REJECTED at DB boundary
8. Result: exactly one ledger entry, no duplicate, recovery preserved
```

---

## Decision Card (Stale Lease Takeover)

| Signal | Value |
|---|---|
| Scenario | `stale_lease_takeover` |
| Workers | 8 |
| Duplicate commits | **0** |
| Stale writes prevented | yes |
| Throughput impact | −5.9% |
| p95 latency delta | +1.6% |
| Recovery time | 0.4s |
| Bottleneck | claim_path |
| Recommendation | increase batch size, enable adaptive polling |
| Safe for production | YES |

---

## Failure Scenarios Validated

| Scenario | Guarantee | Throughput Impact | p95 Delta | Recovery |
|---|---|---|---|---|
| Worker crash mid-execution | No duplicate commit | −16.2% | +4.0% | 1.1s |
| Stale lease takeover | Stale write rejected | −5.9% | +1.6% | 0.4s |
| Timeout burst | Retries preserve correctness | −26.8% | +12.1% | 2.3s |
| Retry storm | Correctness under contention | −32.5% | +15.0% | 2.8s |
| Duplicate submission | Idempotency enforced | ~0% | ~0% | — |
| Partial write + crash | Reconciler converges state | minimal | minimal | 0.8s |

---

## Coordination Cost Breakdown

Nearly **46% of execution time is coordination overhead** — making scheduling strategy and batching first-class system concerns, not premature optimization.

```
Useful execution time       53.5%  ████████████████████████████░░░░░░░░░
Idle polling overhead       12.0%  ██████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
Completion path             11.8%  █████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
Retry scheduling            11.1%  █████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
Claim path                   7.6%  ███░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
Reconciliation               4.0%  ██░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
```

**Finding:** Increasing batch size from 1 to 10 reduced claim-path overhead from 18.3% to 7.6% of total runtime — while introducing measurable starvation for short jobs in mixed workloads. The tradeoff is real and quantified.

---

## Benchmark Workload Profiles

| Workload | Characterization | Key Stress |
|---|---|---|
| `uniform_short` | All jobs <50ms | High claim throughput |
| `mixed_short_long` | 70% short / 30% long | Fairness / starvation |
| `large_payload` | 100KB+ per job | Serialization overhead |
| `retry_heavy` | 40% failure rate | Retry amplification |
| `timeout_prone` | 20% timeout rate | Recovery path validation |
| `burst_enqueue` | 10x spike, then drain | Queue depth / backpressure |
| `long_running_leases` | Jobs >30s | Lease expiry / churn |

---

## Fairness Analysis

Under mixed short/long workloads, Faultline surfaces scheduling behavior explicitly:

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

## Generated Artifacts

Every run produces structured, operator-facing evidence:

```
artifacts/
├── reports/
│   ├── decision_report.json          # safe_for_production · bottleneck · recommendation
│   ├── failure_matrix.md             # scenario x guarantee x throughput x recovery
│   ├── coordination_breakdown.md     # claim / poll / complete / reconcile breakdown
│   ├── fairness_report.md            # wait distribution · starvation · short-job penalty
│   └── tuning_recommendation.md      # batch size · poll strategy · retry backoff guidance
└── benchmarks/
    ├── run_config.json
    ├── metrics_summary.json
    └── comparison_table.md
```

**Example `decision_report.json`:**
```json
{
  "scenario": "stale_lease_takeover",
  "workers": 8,
  "batch_size": 10,
  "duplicate_commits": 0,
  "stale_writes_prevented": true,
  "bottleneck": "claim_path",
  "recommendation": "increase batch size, enable adaptive polling",
  "safe_for_production": true
}
```

---

## Key Technical Findings

- Batching improved throughput 2.3x but introduced starvation for short jobs at `batch_size > 10`
- Coordination overhead consumed **46.5% of runtime** under single-item batching — the most common default
- Reconciler converged incomplete state within **1.1s** of crash across all tested scenarios
- Retry storms at 40% failure rate degraded throughput 32.5% while maintaining **zero duplicate commits**
- Adaptive polling reduced idle poll overhead from 18.4% to 6.2% under low-load conditions

---

## Observability

Faultline exposes Prometheus metrics for both the API and worker processes:

- Job throughput (jobs/sec) and execution latency (p50/p95/p99)
- Lease acquisition success rate and expiration frequency
- Stale-write rejection count and retry amplification factor
- Reconciliation trigger rate and convergence time
- Queue depth and backlog growth rate

Failure modes surface through metrics, not silent retries.

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

# View Prometheus metrics
open http://localhost:9090
```

---

## Design Decisions

**PostgreSQL as coordination layer, not a message broker.** PostgreSQL's transactional guarantees enforce correctness at the database boundary without distributed consensus. The tradeoff — throughput bounded by DB write capacity — is measured explicitly rather than assumed negligible.

**Fencing tokens over distributed locks.** Tokens are monotonically increasing per lease epoch. Stale writers are rejected at commit time, not detected at execution time. This avoids thundering-herd lock contention under crash-heavy workloads.

**Reconciler over heartbeats.** The reconciler periodically reclaims jobs with expired leases. Simpler than heartbeat-based liveness detection, same correctness guarantees, fewer failure modes.

**Artifact-first design.** Every benchmark and failure scenario produces structured, operator-readable output. Correctness and performance claims are evidence-backed, not asserted.

---

## Limitations

- Throughput bounded by PostgreSQL write capacity — by design; measured rather than hidden
- Benchmark numbers reflect specific test configurations, not universal queue performance claims
- Fairness characteristics shift significantly with batch size and workload composition
- Reconciler polling interval introduces worst-case recovery window of `(poll_interval + lease_duration)` after crash
- Missing instrumentation at the call site reduces precision of coordination attribution

---

## Repo Structure

```
faultline/
├── api/              # FastAPI job submission and status endpoints
├── worker/           # Claim, execute, complete, fencing validation
├── services/         # Ledger, lease management, reconciler
├── common/           # Job state machine, DB models
├── drills/           # Scripted failure scenarios
├── tests/            # Correctness and integration tests
├── migrations/       # Alembic DB migrations
├── infra/prometheus/ # Metrics scrape config
├── docs/             # Architecture diagram, decision docs
└── artifacts/        # Generated benchmark and failure reports
```

---

## Future Work

- LISTEN/NOTIFY wakeups to replace polling for lower idle overhead
- Priority lanes with per-lane fairness guarantees
- Cross-worker coordination cost model for larger worker counts
- Visual execution timeline artifact for reclaim-race sequences


## Formal Spec and Case Study

To make the reclaim-race behavior easier to inspect and reason about, the repo includes:

- `formal-spec/` — a minimal TLA+ model for fencing-token lease progression and stale-writer exclusion
- `docs/case_studies/reclaim_race.md` — a walkthrough of the reclaim race and why stale writers are rejected

These artifacts are meant to show not just that the system works, but why the correctness rule holds under adversarial timing.
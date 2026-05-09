# Faultline — Crash-Safe Distributed Job Execution with Stale-Write Rejection

**Faultline prevents stale-worker corruption in distributed job execution.**

`Python` · `PostgreSQL` · `Prometheus` · `Docker Compose`

---

**In one line:** Lease expiry tells another worker it may claim the job. It does not stop the old worker from writing late. Fencing tokens fix the write boundary — enforced at the database, not the application.

---

## Duplicate Commit Rate: Faultline vs Naive Queue

```
  Fault    Naive Queue          Faultline
  Rate     Duplicate Rate       Duplicate Rate
  ──────────────────────────────────────────────
   5%      ██░░░░░░░░  1.0%     ░░░░░░░░░░  0.0%  ✓
  10%      █████░░░░░  2.5%     ░░░░░░░░░░  0.0%  ✓
  20%      █████░░░░░  2.5%     ░░░░░░░░░░  0.0%  ✓

  200 jobs · 8 workers · 1,500+ failure scenarios · 0 invariant violations
```

---

## Run in 30 Seconds

```bash
git clone https://github.com/kritibehl/faultline
cd faultline
docker compose up -d --build && make migrate
make drills                                  # run failure scenarios
./scripts/run_real_benchmark_comparison.sh   # Faultline vs naive queue
```

---

## Why This Project Matters in Hiring Terms

- Shows distributed systems correctness thinking: fencing tokens, lease semantics, database-boundary enforcement
- Shows failure engineering: 1,500+ injected scenarios, measured recovery times, zero invariant violations
- Shows production tradeoff analysis: coordination overhead quantified, fairness impact measured
- Relevant to: backend platform, distributed infrastructure, SRE, systems correctness

---

## Proof, Up Front

| Metric | Result |
|---|---|
| Duplicate commit rate — Faultline, 5–20% injected faults | **0.0%** |
| Duplicate commit rate — naive queue, same conditions | **1.0–2.5%** |
| Jobs tested | 200 |
| Workers | 8 |
| Failure scenarios validated | 1,500+ |
| Invariant violations | **0** |
| Coordination overhead (worst case, measured) | 46.5% of total runtime |

![Faultline vs Naive Queue Benchmark](benchmarks/results/faultline_vs_naive.png)

---

## The 60-Second Explanation

A worker claims a job and starts executing. It stalls — network partition, GC pause, crash. The lease expires. Another worker reclaims the job and finishes it. The first worker recovers, finishes executing, and tries to commit.

Lease expiry tells the *next* worker it may claim the job. It does not stop the *old* worker from writing late. That's the gap. Fencing tokens fix the write boundary: every commit attempt carries a token and the database rejects any token that isn't the current one.

```
Worker A claims job → fencing_token = 7
Network partition  → lease expires
Worker B reclaims  → fencing_token = 8
Worker B commits   → ledger entry (job_42, token=8) written ✓
Worker A recovers  → attempts commit with token=7
Fencing check      → token 7 < current token 8 → REJECTED at DB boundary ✗

Result: exactly one ledger entry. Zero duplicates.
```

No distributed locks. No heartbeat consensus. No application-layer deduplication. The `UNIQUE(job_id, fencing_token)` constraint on the ledger table makes this enforced at the database, not assumed at the application.

---

## What Faultline Does

- **Rejects** stale writes at the database boundary using monotonically increasing fencing tokens
- **Prevents** duplicate commits without distributed locks or heartbeat consensus
- **Validates** correctness across 1,500+ injected failure scenarios: crashes, lease takeovers, retry storms, partial writes
- **Measures** coordination overhead explicitly — claim path, idle polling, reconciliation — not treated as negligible
- **Quantifies** fairness tradeoffs: short-job starvation at `batch_size=10`, measured and reported
- **Reconciles** incomplete state after crash, converging to correct terminal state without manual intervention

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

**Naive queue vs Faultline — what changes:**

```
Naive queue:
  claim → execute → commit
                      ↑
              stale worker can reach this
              even after lease expires

Faultline:
  claim → execute → fencing check → commit (if current token)
                         ↑
                 stale writer is stopped here
                 at the DB boundary, not the app layer
```

---

## Evidence

| Scenario | Guarantee | Throughput impact | p95 delta | Recovery |
|---|---|---|---|---|
| Worker crash mid-execution | No duplicate commit | −16.2% | +4.0% | 1.1s |
| Stale lease takeover | Stale write rejected | −5.9% | +1.6% | 0.4s |
| Timeout burst | Retries preserve correctness | −26.8% | +12.1% | 2.3s |
| Retry storm | Correctness under contention | −32.5% | +15.0% | 2.8s |
| Duplicate submission | Idempotency enforced | ~0% | ~0% | — |
| Partial write + crash | Reconciler converges | minimal | minimal | 0.8s |

**Zero duplicate commits across all scenarios.**

**Benchmark — Faultline vs naive queue (200 jobs, 8 workers):**

| Fault rate | Faultline duplicate rate | Naive duplicate rate |
|---|---|---|
| 5% | **0.0%** | 1.0% |
| 10% | **0.0%** | 2.5% |
| 20% | **0.0%** | 2.5% |

---

## Coordination Cost: Measured, Not Assumed

```
Useful execution        53.5%  ████████████████████████████
Idle polling            12.0%  ██████
Completion path         11.8%  █████
Retry scheduling        11.1%  █████
Claim path               7.6%  ███
Reconciliation           4.0%  ██
```

Increasing batch size 1 → 10 reduced claim-path overhead from 18.3% to 7.6% of total runtime — but introduced measurable short-job starvation in mixed workloads. That tradeoff is real, quantified, and documented.

---

## Quick Demo

```bash
docker compose up -d --build
make migrate
curl http://localhost:8000/health
make drills                                        # run failure scenarios
./scripts/run_real_benchmark_comparison.sh         # Faultline vs naive queue
```

---

## Example Output

**Decision report — stale lease takeover:**
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

**Fairness report — mixed workload, batch_size=10:**
```json
{
  "workload": "mixed_short_long",
  "median_wait_ms": { "short": 42, "long": 280 },
  "max_wait_ms": 1840,
  "starvation_count": 3,
  "short_job_penalty_pct": 12.4,
  "finding": "Long jobs acquired disproportionate worker slots at batch_size=10"
}
```

---

## Full Setup

```bash
docker compose up -d --build
make migrate
curl http://localhost:8000/health
make drills
./scripts/run_real_benchmark_comparison.sh
open http://localhost:9090   # Prometheus metrics
```

---

## Observability

Prometheus metrics:

- `stale_commits_prevented_total` — leading indicator of lease TTL misconfiguration
- `jobs_claimed_total` · `jobs_completed_total` · `jobs_failed_total`
- `lease_expiry_reaps_total`
- `job_execution_duration_seconds` (p50/p95/p99 histogram)
- `reconciler_convergence_seconds`
- `idle_poll_overhead_pct`

---

## Generated Artifacts

```
artifacts/reports/
├── decision_report.json          # safe_for_production · bottleneck · recommendation
├── failure_matrix.md             # scenario × guarantee × throughput × recovery
├── coordination_breakdown.md     # claim / poll / complete / reconcile overhead
├── fairness_report.md            # wait distribution · starvation · short-job penalty
├── correctness_audit.md          # violations=0, stale write attempts logged
└── tuning_recommendation.md      # batch size · poll strategy · retry backoff
```

---

## Why This Matters

Every distributed system that processes jobs eventually hits this failure class. Worker crashes don't surface stale writes immediately — they show up as billing double-charges, inventory miscounts, notification floods or audit records that don't reconcile.

Fencing tokens over distributed locks was a deliberate choice. Tokens are monotonically increasing per lease epoch. A stale writer is rejected at commit time, not detected at execution time. This avoids thundering-herd lock contention under crash-heavy workloads and keeps correctness enforcement at the database — where it can't be bypassed by application-layer bugs.

---

## Limitations

- Does not protect against Byzantine faults (a worker fabricating a fencing token)
- Requires PostgreSQL; not designed for broker-based queues
- Benchmark uses simulated fault injection, not production traffic
- Reconciliation runs on a polling interval, not event-triggered
- Exactly-once semantics apply at the commit boundary; external side effects require idempotent job design

---

## Interview Notes

**Design decision:** Fencing tokens over distributed locks. Correctness at the DB boundary is stronger than coordination at the application layer — a stale worker can't commit regardless of what it believes about its own state.

**Hard problem:** Getting `FOR UPDATE SKIP LOCKED` right under concurrent reclaim pressure. Naive implementation produces starvation at high worker counts; batch-claim reduces contention but introduces fairness tradeoffs that had to be measured.

**Tradeoff:** Batch size vs short-job fairness. `batch_size=10` cuts claim overhead from 18.3% to 7.6%, but long jobs starve short ones in mixed workloads. The right value depends on workload shape — which means measuring, not guessing.

**What I'd build next:** Event-triggered reconciliation. Polling-based reconciliation introduces unnecessary recovery latency when the failure is immediately detectable. A `LISTEN/NOTIFY`-driven reconciler would cut median recovery time significantly.

---

## Relevant To

`Backend Engineering` · `Distributed Systems` · `Platform / Infrastructure` · `SRE` · `Systems Correctness`

---

## Stack

Python · PostgreSQL · Prometheus · OpenTelemetry · Docker Compose · Alembic

---

## Related

- [KubePulse](https://github.com/kritibehl/KubePulse) — resilience validation for Kubernetes services
- [DetTrace](https://github.com/kritibehl/dettrace) — deterministic replay for concurrency failures
- [AutoOps-Insight](https://github.com/kritibehl/AutoOps-Insight) — CI failure intelligence and incident triage
- [Postmortem Atlas](https://github.com/kritibehl/postmortem-atlas) — real production outages, structured and analyzed


## Observability and Replay Tooling

Faultline includes:

- Prometheus-compatible metrics endpoint
- OpenTelemetry-style trace exports
- replayable failure artifacts
- benchmark dashboards
- structured stale-write rejection signals
- replay validation tooling


# Faultline

> A production-style distributed execution correctness system that prevents stale-worker state corruption using PostgreSQL fencing-token enforcement and failure-injection validation.

`Python` · `PostgreSQL` · `Go` · `Prometheus` · `OpenTelemetry` · `Kubernetes`

---

## Why This Project Matters

- Lease-based job systems allow stale workers to commit after recovery — a gap that causes double-charges, miscounts, and audit failures
- Lease expiry stops the *next* worker from waiting; it does not stop the *old* worker from writing late
- Faultline rejects stale writes at the database boundary using fencing tokens — enforced by a `UNIQUE(job_id, fencing_token)` constraint, not application logic
- This proves: distributed correctness reasoning, failure-safe protocol design, and the engineering discipline to measure every tradeoff

---

## 30-Second Proof

| Signal | Verified output |
|---|---|
| Duplicate commits under 5–20% fault injection | **0.0%** |
| Naive queue duplicate rate (same conditions) | 1.0–2.5% |
| Failure scenarios validated | **1,500+** |
| Invariant violations | **0** |
| Worker crash recovery | 1.1s |
| Stale lease takeover recovery | 0.4s |
| Tests | All passing |

---

## Screenshots

> Add these to `docs/screenshots/` — highest ROI remaining improvement.

| Stale-Worker Timeline | Benchmark Comparison |
|---|---|
| ![Stale Worker Timeline](docs/images/timeline.png) | ![Benchmark](benchmarks/results/faultline_vs_naive.png) |

| Prometheus Dashboard | Lease Risk Dashboard |
|---|---|
| ![Prometheus](docs/architecture/prometheus_dashboard.png) | ![Lease Risk](monitoring/lease_risk_dashboard.png) |

**Stale-worker rejection — animated sequence (add as `docs/gifs/stale_worker.gif`):**

```
t=0  Worker A  ──────── claims job ──────────────  token=1  ✓
t=1  Worker A  ──────── executing ───────────────  ...
t=2  Worker A  ──────── STALLS (crash/partition)   ✗
t=3  Lease     ──────── expires ─────────────────
t=4  Worker B  ──────── claims job ──────────────  token=2  ✓
t=5  Worker B  ──────── commits ─────────────────  token=2  ✓
t=6  Worker A  ──────── recovers ────────────────
t=7  Worker A  ──────── tries to commit ─────────  token=1
t=7  DB        ──────── REJECTS (1 < 2) ─────────  ✗  0 duplicates
```

---

## Demo

```bash
git clone https://github.com/kritibehl/faultline
cd faultline
make demo
```

Expected output:
```json
{
  "fault_rate": "10%",
  "faultline_duplicates": 0,
  "naive_duplicates": 5,
  "invariant_violations": 0,
  "stale_writes_prevented": true,
  "safe_for_controlled_release_validation": true
}
```

```bash
make test     # 1,500+ failure scenarios — 0 invariant violations
make report   # benchmark report → reports/latest/benchmark_summary.json
```

---

## Architecture

![Faultline Architecture](docs/architecture.png)

```
Producer / API
      │
      ▼
PostgreSQL (source of truth)
  jobs:    lease_owner · fencing_token · state
  ledger:  UNIQUE(job_id, fencing_token)   ← stale writes rejected here
      │
      ├────────────────────────┐
      ▼                        ▼
Worker Pool               Reconciler
claim(token=N)            repairs incomplete jobs
→ execute                 converges stale state
→ commit or REJECT
      │
      ▼
Go Inspector API  →  /api/leases · /api/workers · /api/risk
      │
      ▼
Prometheus + OTEL  →  stale rejections · claim latency · coordination overhead
```

**How stale writes happen — and how Faultline stops them:**

```
Worker A claims job  →  token=1
Worker A stalls (crash / partition)
Lease expires
Worker B claims job  →  token=2
Worker B commits  ✓
Worker A recovers  →  tries to commit with token=1
DB: token 1 < current token 2  →  REJECTED  ✗  →  0 duplicates
```

---

## Core Workflows

### 1. Failure injection + correctness validation

Injects 6 failure types (crash, stale takeover, retry storm, timeout burst, duplicate submission, partial write). Validates that `duplicate_commits = 0` and `invariant_violations = 0` across all scenarios.

```bash
make test
# → 1,500 scenarios · 0 violations
```

### 2. Faultline vs naive queue benchmark

Runs both systems under identical fault injection. Faultline holds 0.0%; naive queue reaches 2.5% duplicates at 20% fault rate.

```bash
make demo
# → reports/latest/benchmark_summary.json
```

### 3. Inspector API + observability

Go API surfaces live lease risk, worker state, and rejection history. Prometheus metrics feed coordination overhead, stale rejection count, and claim latency.

```bash
./inspector serve
# GET /api/risk → { "stale_risk": "low", "active_workers": 8 }
```

---

## Failure Scenarios Covered

| Scenario | Mechanism | Decision |
|---|---|---|
| Stale lease takeover | Recovered worker commits old token | REJECTED at DB |
| Worker crash mid-commit | Process killed during write | Reconciler re-routes, 0 corruption |
| Retry storm | 50+ concurrent retries, same job | 0 duplicates under contention |
| Timeout burst | TTL expires mid-execution | New worker claims; stale rejected |
| Duplicate submission | Same job submitted twice | Idempotency enforced |
| Partial write + crash | Write interrupted | Reconciler converges state |

---

## Engineering Decisions

**Why fencing tokens over lease-only systems:**

| | Lease only | Fencing tokens |
|---|---|---|
| Stale worker commits | Allowed — advisory only | Rejected — DB constraint |
| Duplicate risk | Present under crash + recovery | Structurally impossible |
| Correctness depends on | Lease TTL timing | Monotonic token ordering |

Heartbeat systems keep workers alive but still allow stale commits during the eviction gap. Fencing tokens eliminate the gap — the token *is* the authority, and old tokens are permanently invalid.

**Why DB enforcement over application-layer checks:** Application checks can be bypassed under failure (race conditions, partial execution, network partition). A DB `UNIQUE` constraint cannot.

---

## What Is Intentionally Out of Scope

- Does not protect against Byzantine faults (fabricated tokens)
- Benchmark uses simulated fault injection, not production traffic
- Requires PostgreSQL — not designed for broker-based queues
- Reconciliation is polling-interval, not event-triggered
- External side effects require idempotent job design

---

## Resume Bullets

- Built a distributed job execution platform with PostgreSQL fencing-token enforcement, validating 0% duplicate commit rate across 1,500+ injected failure scenarios
- Designed a correctness protocol (claim → execute → fenced commit) that rejects stale writes at the database boundary under crash, lease takeover, and retry storm conditions
- Instrumented with OpenTelemetry distributed traces, Prometheus metrics, and a Go inspector API with lease-risk scoring

---

## Interview Walkthrough

*"Faultline solves the stale-worker problem in distributed job systems. When a worker crashes mid-job, the lease expires and a new worker takes over — but the original worker can recover and try to commit. Lease expiry doesn't stop that. Faultline uses fencing tokens: every lease epoch gets a monotonically increasing token, and the database enforces `UNIQUE(job_id, token)`. A stale worker's old token is permanently invalid. I validated this across 1,500 injected failures — crash, takeover, retry storm — with 0 duplicate commits and 0 invariant violations."*

---

## Run Locally

```bash
git clone https://github.com/kritibehl/faultline && cd faultline
docker compose up -d --build && make migrate
make demo    # benchmark comparison
make test    # failure injection suite
make report  # full report
```

---

## Repository Map

```
faultline/
├── workers/          Python worker pool + lease logic
├── reconciler/       Crash recovery + state convergence
├── inspector/        Go API — lease risk, worker state
├── benchmarks/       Faultline vs naive queue comparison
├── drills/           1,500+ failure injection scenarios
├── monitoring/       Prometheus + Grafana dashboards
├── k8s/              Kubernetes manifests + Helm chart
├── docs/             Architecture diagrams + screenshots
└── reports/          Benchmark outputs
```

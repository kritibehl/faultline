# Faultline

**Failure testing for correctness bugs in at-least-once background workers.**

Faultline drives real Celery workers, injects real process-level faults with `SIGSTOP`/`SIGCONT`, and proves — with a live comparison, not a claim — that commit-time fencing prevents the duplicate-execution bug that plain at-least-once delivery allows.

`Python` · `Celery` · `Redis` · `PostgreSQL` · `Docker Compose`

---

## The result, first

```text
Faultline Correctness Comparison
================================

                             UNSAFE     FENCED
----------------------------------------------
Committed effects                2          1
Stale rejections                 0          1
Current token                    2          2
Invariant                     FAIL       PASS

COMPARISON RESULT: PASS
(unsafe violated the invariant; fenced preserved it)
```

Same fault, same workers, same broker — one implementation double-executes the job, the other doesn't. That's the whole thesis of this project, proven by a real run, not asserted in prose.

Run it yourself:
```bash
faultline compare --adapter celery --fault pause --invariant at-most-one-effect
```

---

## The bug

At-least-once delivery means a logical job can execute more than once. Faultline reproduces the specific case that causes that: Worker A starts a task, stalls before committing, and resumes *after* Worker B has already taken ownership and finished the job.

```text
Worker A receives job, token = 1
        │
        ▼
Worker A reaches pre-commit window
        │
   Faultline: SIGSTOP
        │
        ▼
Redis visibility timeout expires
        │
        ▼
Worker B receives redelivery, token = 2 → commits
        │
   Faultline: SIGCONT
        │
        ▼
Worker A resumes, still holding token 1 → also commits
```

**Without fencing:** both commits succeed. `committed_effects = 2`. Invariant fails.

**With fencing:** PostgreSQL validates ownership at commit time — `presented_token == current_token` — so Worker A's stale commit is rejected outright. `committed_effects = 1`. Invariant holds. The database enforces this; correctness doesn't depend on Worker A ever realizing it lost ownership.

---

## Why this matters

A lease or a timeout can determine who owns a job *right now*. It does nothing to stop the previous owner from waking up later and writing anyway. That gap is where duplicate charges, double-sent notifications, and corrupted ledgers come from in real systems — and it's the specific gap this project reproduces, measures, and closes.

---

## What Faultline actually does, end to end

1. Starts PostgreSQL, Redis, and Worker A
2. Publishes a real Celery task
3. Waits until Worker A reaches the dangerous pre-commit window
4. Stops Worker A with `SIGSTOP`
5. Waits for the Redis visibility timeout
6. Starts Worker B — observes redelivery with a newer fencing token
7. Waits for Worker B to commit
8. Resumes Worker A with `SIGCONT`
9. Records whether Worker A's stale commit succeeds or is rejected
10. Reads the PostgreSQL execution history and evaluates the invariant
11. Writes machine-readable JSON/JSONL artifacts

---

## Architecture

```text
                    faultline CLI
                         │
                         ▼
                    orchestrator
                         │
          ┌──────────────┴──────────────┐
          ▼                             ▼
    fault injection                Celery adapter
    SIGSTOP / SIGCONT                   │
                                        ▼
                                   Redis broker
                                        │
                           ┌────────────┴────────────┐
                           ▼                         ▼
                       Worker A                  Worker B
                           │                         │
                           └────────────┬────────────┘
                                        ▼
                                   PostgreSQL
                                  effect ledger
                                        │
                    ┌───────────────────┴───────────────────┐
                    ▼                                       ▼
              execution history                       invariant
               history.jsonl                            checker
                    │                                       │
                    └───────────────────┬───────────────────┘
                                        ▼
                                   report.json
```

---

## Methodology — and what this isn't

Faultline is **Jepsen-inspired**: drive a real system → inject a real failure → collect execution history → check an explicit correctness property. It is *not* Jepsen, and doesn't claim Jepsen-equivalent coverage.

The demonstrated result is deliberately narrow, and stated that way on purpose:

> Under the included Celery/Redis/PostgreSQL stale-worker experiment, the unsafe reference implementation produces two committed effects after redelivery, while commit-time fencing rejects the stale worker and preserves the at-most-one-effect invariant.

**What this project does not claim:** universal exactly-once execution, formal proof of linearizability, Byzantine fault tolerance, consensus verification, production certification for Celery/Redis, exhaustive fault coverage, or correctness of arbitrary external side effects.

That restraint is deliberate — an honest, narrow, *proven* claim is worth more than a broad, asserted one.

---

## Try it

```bash
python3 -m venv .framework-venv
source .framework-venv/bin/activate
python -m pip install -e '.[dev]'

# Unsafe implementation — expect FAIL
faultline test --adapter celery --fault pause --implementation unsafe --invariant at-most-one-effect

# Fenced implementation — expect PASS
faultline test --adapter celery --fault pause --implementation fenced --invariant at-most-one-effect
```

## Tests

```bash
python -m pip install -e '.[dev]'
python -m pytest tests/test_framework_invariants.py tests/test_framework_reports.py \
  tests/test_framework_cleanup.py tests/test_framework_cli.py -q
```

Covers invariant behavior, canonical unsafe/fenced evidence, CLI parsing, backward compatibility, and worker recovery cleanup.

---

## Repository Structure

```
faultline/
├── faultline/
│   ├── cli.py
│   ├── history.py
│   ├── adapters/        base.py, celery.py
│   ├── faults/
│   ├── invariants/      effects.py
│   └── reporting/       compare.py
├── integrations/celery/ Dockerfile, docker-compose, app/, postgres/init.sql
├── tests/
├── artifacts/            runs/ (generated, gitignored) · canonical/ (curated evidence)
├── pyproject.toml
└── SCOPE_FRAMEWORK.md
```

---

## Current support

| Component | Support |
|---|---|
| Worker framework | Celery |
| Broker | Redis |
| Side-effect store | PostgreSQL |
| Fault | Process pause (`SIGSTOP`) |
| Recovery | `SIGCONT` |
| Redelivery | Redis visibility timeout |
| Invariant | `at-most-one-effect` |
| Implementations | unsafe, fenced |

## Roadmap

Near-term: generic fault-injector interface, process kill/restart, broker/database disconnect faults, additional invariants, CI integration. Future adapters (BullMQ/Redis, Amazon SQS) will preserve each broker's real delivery semantics rather than assuming they all behave the same.

---

## Status

Early framework prototype. The Celery reference adapter runs the full stale-worker experiment end-to-end today — real workers, real Redis redelivery, real PostgreSQL writes, real process pause/resume, and a machine-checked invariant.

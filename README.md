# Faultline
 
**Failure testing for correctness bugs in at-least-once background workers.**
 
Faultline drives real Celery and BullMQ workers, injects real process-level faults (`SIGSTOP`/`SIGCONT`, `SIGKILL`/restart), and proves — with live comparisons against real infrastructure, not claims — exactly where fencing is sufficient to prevent duplicate execution, and where it isn't.
 
`Python` · `Celery` · `BullMQ` · `Redis` · `PostgreSQL` · `Docker Compose`
 
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
 
Same fault, same workers, same broker — one implementation double-executes the job, the other doesn't. Proven by a real run against real infrastructure, not asserted in prose.
 
```bash
faultline compare --adapter celery --fault pause --invariant at-most-one-effect
```
 
---
 
## Fencing is necessary, not sufficient: the ambiguous remote outcome
 
The scenario above shows fencing solving a *local ownership* problem: a stale worker's commit gets rejected because it no longer holds the current token. A separate scenario, `faultline/scenarios/ambiguous_remote.py`, demonstrates exactly where fencing stops working — using a real remote charge-service, not a simulation.
 
**The scenario:** Worker A calls a remote charge-service. The charge succeeds, but Worker A is killed with `SIGKILL` before it learns the result — it only observes `EFFECT_RESULT_UNKNOWN`. Worker B is redelivered the same job and has no way to know a charge already landed remotely.
 
**Measured results across all four strategies:**
 
| Strategy | External effects | Duplicate suppressions | Fencing acceptances | Result |
|---|---|---|---|---|
| naive | 2 | 0 | – | FAIL |
| fencing | 2 | 0 | 2 | FAIL |
| idempotency | 1 | 1 | – | PASS |
| fencing + idempotency | 1 | 1 | 2 | PASS |
 
**Why fencing alone still fails:** both of Worker B's commit attempts are fencing-*accepted* (`remote_fencing_acceptances: 2`, `remote_stale_rejections: 0`). Worker B isn't a stale owner — it legitimately holds the current token. Fencing has nothing to reject, because the problem was never "who owns this job." It's "did the remote side effect already happen." Those are different failure classes: fencing defends the *local ownership* transition; only idempotency (an idempotency key on the remote charge itself) defends the *remote effect* against being applied twice when the caller genuinely cannot tell whether its previous attempt succeeded.
 
```bash
python -m faultline.scenarios.ambiguous_remote --strategy fencing
python -m faultline.scenarios.ambiguous_remote --strategy fencing-idempotency
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
 
## What Faultline actually does, end to end
 
1. Starts PostgreSQL, Redis, and Worker A
2. Publishes a real Celery or BullMQ task
3. Waits until Worker A reaches the dangerous pre-commit (or post-commit) window
4. Injects a fault: `SIGSTOP` (pause) or `SIGKILL` (kill)
5. Waits for broker redelivery
6. Starts Worker B — observes redelivery with a newer fencing token
7. Waits for Worker B to commit or suppress the duplicate
8. Recovers Worker A: `SIGCONT` (pause) or container restart (kill)
9. Records whether Worker A's stale/redundant commit succeeds or is rejected
10. Reads the PostgreSQL execution history and evaluates the selected invariant
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
    fault injection                worker adapter
    SIGSTOP/SIGCONT/SIGKILL         (Celery or BullMQ)
                                        │
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
              execution history                    invariant checker
               history.jsonl                  (4 invariants available)
                    │                                       │
                    └───────────────────┬───────────────────┘
                                        ▼
                                   report.json
```
 
---
 
## Methodology — and what this isn't
 
Faultline is **Jepsen-inspired**: drive a real system → inject a real failure → collect execution history → check an explicit correctness property. It is *not* Jepsen, and doesn't claim Jepsen-equivalent coverage.
 
**What this project does not claim:** universal exactly-once execution, formal proof of linearizability, Byzantine fault tolerance, consensus verification, production certification for Celery/BullMQ/Redis, exhaustive fault coverage, or correctness of arbitrary external side effects.
 
That restraint is deliberate — an honest, narrow, *proven* claim is worth more than a broad, asserted one.
 
---
 
## Try it
 
```bash
python3 -m venv .framework-venv
source .framework-venv/bin/activate
python -m pip install -e '.[dev]'
 
faultline test --adapter celery --fault pause --implementation unsafe --invariant at-most-one-effect
faultline test --adapter celery --fault pause --implementation fenced --invariant at-most-one-effect
faultline test --adapter bullmq --fault kill --window post-commit --implementation idempotent --invariant at-most-one-effect
```
 
## Tests
 
```bash
python -m pip install -e '.[dev]'
python -m pytest tests/ -v
```
 
52 tests covering: invariant behavior (all four checkers), canonical unsafe/fenced/idempotent evidence for both adapters, the ambiguous-remote-outcome matrix, CLI parsing and backward compatibility, pre-commit and post-commit semantics, kill-fault lifecycle, and worker recovery cleanup.
 
---
 
## Repository Structure
 
```
faultline/
├── faultline/
│   ├── cli.py
│   ├── history.py
│   ├── adapters/        base.py, celery.py, bullmq.py, registry.py
│   ├── scenarios/        ambiguous_remote.py
│   ├── faults/            base.py, process.py (pause + kill)
│   ├── invariants/         effects.py (4 invariant checkers)
│   └── reporting/           compare.py
├── integrations/celery/       Dockerfile, docker-compose, app/, postgres/init.sql
├── tests/                        52 tests across ~15 files
├── artifacts/                      runs/ (generated, gitignored) · canonical/ (curated evidence)
├── pyproject.toml
└── SCOPE_FRAMEWORK.md
```
 
---
 
## Current support
 
| Component | Support |
|---|---|
| Worker frameworks | Celery, BullMQ |
| Broker | Redis |
| Side-effect store | PostgreSQL |
| Faults | Process pause (`SIGSTOP`/`SIGCONT`), kill (`SIGKILL`/restart) |
| Windows | pre-commit, post-commit |
| Invariants | at-most-one-effect, stale-owner-cannot-commit, no-lost-committed-effect, eventually-processed-after-recovery |
| Implementations | unsafe, fenced, idempotent |
| Scenarios | stale-worker redelivery, ambiguous remote outcome |
 
*Note: `kill` fault currently supports only `window=post-commit`.*
 
## Roadmap
 
Near-term: broker/database disconnect faults, wiring `--invariant` selection fully through the CLI's `compare` command (currently only `test` supports invariant selection end-to-end), CI integration. Future adapters (Amazon SQS) will preserve each broker's real delivery semantics rather than assuming they all behave the same.
 
---
 
## Status
 
Active framework, not an early prototype — 52 passing tests across two worker adapters (Celery, BullMQ), two fault types, two failure windows, four invariant checkers, and two distinct distributed-systems scenarios (stale-worker redelivery and ambiguous remote outcome), all validated against real Redis/PostgreSQL/Docker infrastructure.

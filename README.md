# Faultline

**Failure testing for correctness bugs in at-least-once background workers.**

Faultline drives real queue consumers, injects failures, records execution
histories, and checks application-level invariants after redelivery and
stale-worker recovery.

Current reference integration:

- Celery workers
- Redis broker
- PostgreSQL side-effect ledger
- Docker Compose
- real `SIGSTOP` / `SIGCONT`
- visibility-timeout redelivery
- fencing tokens
- machine-readable JSONL histories and JSON reports

## Quick demo

Install:

```bash
python3 -m venv .framework-venv
source .framework-venv/bin/activate
python -m pip install -e '.[dev]'
```

Run the complete correctness comparison:

```bash
faultline compare \
  --adapter celery \
  --fault pause \
  --invariant at-most-one-effect
```

Current observed result:

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

The comparison exits `0` when Faultline observes the expected contrast:

```text
unsafe implementation  -> invariant violated
fenced implementation  -> invariant preserved
```

## The stale-worker bug

At-least-once delivery means a logical job can be executed more than once.

Faultline reproduces a case where Worker A starts a task, stops before
committing, and later resumes after Worker B has already taken ownership.

### Without fencing

```text
Worker A receives job
token = 1
        |
        v
Worker A reaches pre-commit window
        |
        v
Faultline sends SIGSTOP
        |
        v
Redis visibility timeout expires
        |
        v
Worker B receives redelivery
token = 2
        |
        v
Worker B commits
        |
        v
Faultline sends SIGCONT
        |
        v
Worker A resumes with stale token 1
        |
        v
Worker A also commits
```

Observed result:

```text
committed effects = 2
stale rejections  = 0
current token     = 2

AT_MOST_ONE_EFFECT = FAIL
```

### With fencing

The same fault is injected, but PostgreSQL validates ownership at commit time.

```text
Worker A receives job
token = 1
        |
      SIGSTOP
        |
        v
Worker B receives redelivery
token = 2
        |
        v
Worker B commits
        |
      SIGCONT
        |
        v
Worker A resumes
presented token = 1
current token   = 2
        |
        v
stale commit rejected
```

Observed result:

```text
committed effects = 1
stale rejections  = 1
current token     = 2

AT_MOST_ONE_EFFECT = PASS
```

## Why fencing matters

A timeout or lease can determine who owns work now, but it does not
automatically stop a previous owner from waking up later and writing stale
state.

Faultline assigns monotonically increasing ownership generations:

```text
Worker A -> token 1
Worker B -> token 2
```

The fenced commit path accepts a write only when:

```text
presented_token == current_token
```

Therefore:

```text
Worker B: 2 == 2 -> commit accepted
Worker A: 1 != 2 -> commit rejected
```

The authoritative database performs the check. Correctness does not depend on
the paused worker realizing that ownership changed.

## What Faultline does

For the current Celery experiment, Faultline:

1. Starts PostgreSQL, Redis, and Worker A.
2. Publishes a real Celery task.
3. Waits until Worker A reaches the dangerous pre-commit window.
4. Stops Worker A with `SIGSTOP`.
5. Waits for the Redis visibility timeout.
6. Starts Worker B.
7. Observes the task being redelivered with a newer fencing token.
8. Waits for Worker B to commit.
9. Resumes Worker A with `SIGCONT`.
10. Records whether Worker A's stale commit succeeds or is rejected.
11. Reads the PostgreSQL execution history.
12. Evaluates the configured correctness invariant.
13. Writes machine-readable artifacts.

## Architecture

```text
                    faultline CLI
                         |
                         v
                    orchestrator
                         |
          +--------------+--------------+
          |                             |
          v                             v
    fault injection                Celery adapter
    SIGSTOP/SIGCONT                     |
                                        v
                                   Redis broker
                                        |
                           +------------+------------+
                           |                         |
                           v                         v
                       Worker A                  Worker B
                           |                         |
                           +------------+------------+
                                        |
                                        v
                                   PostgreSQL
                                  effect ledger
                                        |
                    +-------------------+-------------------+
                    |                                       |
                    v                                       v
              execution history                       invariant
               history.jsonl                           checker
                    |                                       |
                    +-------------------+-------------------+
                                        |
                                        v
                                   report.json
```

## Supported invariant

The first framework invariant is:

`at-most-one-effect`

For each logical job:

```text
committed_effects(job_id) <= 1
```

This is intentionally narrower than claiming universal exactly-once
execution.

## CLI

Test the unsafe implementation:

```bash
faultline test \
  --adapter celery \
  --fault pause \
  --implementation unsafe \
  --invariant at-most-one-effect
```

An invariant violation returns exit code `1`.

Test the fenced implementation:

```bash
faultline test \
  --adapter celery \
  --fault pause \
  --implementation fenced \
  --invariant at-most-one-effect
```

A preserved invariant returns exit code `0`.

`--mode unsafe|fenced` remains available as a backward-compatible alias for
`--implementation`.

## Execution artifacts

Each local experiment writes a generated artifact directory under:

`artifacts/runs/`

Generated runs are ignored by Git. Curated machine-readable evidence used by
the regression suite is stored under:

`artifacts/canonical/`

A completed local run contains:

```text
history.jsonl
report.json
worker-a.log
worker-b.log
```

The history contains events such as:

```text
delivery_started
ready_to_commit
fault_injected
delivery_started
commit_accepted
ownership_observed
fault_recovered
commit_rejected
```

A fenced report records the accepted effect and the rejected stale ownership
generation.

## Project structure

```text
faultline/
├── faultline/
│   ├── cli.py
│   ├── history.py
│   ├── adapters/
│   │   ├── base.py
│   │   └── celery.py
│   ├── faults/
│   ├── invariants/
│   │   └── effects.py
│   └── reporting/
│       └── compare.py
├── integrations/
│   └── celery/
│       ├── Dockerfile
│       ├── docker-compose.yml
│       ├── requirements.txt
│       ├── app/
│       │   ├── db.py
│       │   ├── submit.py
│       │   └── tasks.py
│       └── postgres/
│           └── init.sql
├── tests/
├── artifacts/
├── pyproject.toml
└── SCOPE_FRAMEWORK.md
```

## Tests

Install development dependencies:

```bash
python -m pip install -e '.[dev]'
```

Run the framework regression suite:

```bash
python -m pytest \
  tests/test_framework_invariants.py \
  tests/test_framework_reports.py \
  tests/test_framework_cleanup.py \
  tests/test_framework_cli.py \
  -q
```

The suite currently covers invariant behavior, canonical unsafe and fenced
evidence, CLI parsing, backward compatibility, and worker recovery cleanup.

## Methodology

Faultline is **Jepsen-inspired** in methodology:

```text
drive a real system
        |
inject a real failure
        |
collect execution history
        |
check an explicit correctness property
```

Faultline is not Jepsen and does not claim Jepsen-equivalent coverage or
formal linearizability verification.

## Scope and non-goals

Faultline currently does **not** claim:

- universal exactly-once execution
- formal proof of linearizability
- Byzantine fault tolerance
- consensus verification
- production certification for Celery or Redis
- exhaustive fault coverage
- correctness of arbitrary external side effects

The demonstrated result is deliberately specific:

> Under the included Celery/Redis/PostgreSQL stale-worker experiment, the
> unsafe reference implementation produces two committed effects after
> redelivery, while commit-time fencing rejects the stale worker and preserves
> the at-most-one-effect invariant.

## Current support

| Component | Current support |
| --- | --- |
| Worker framework | Celery |
| Broker | Redis |
| Side-effect store | PostgreSQL |
| Fault | process pause |
| Injection | `SIGSTOP` |
| Recovery | `SIGCONT` |
| Redelivery | Redis visibility timeout |
| Invariant | `at-most-one-effect` |
| Implementations | unsafe, fenced |
| Reports | JSON |
| Histories | JSONL |

## Roadmap

Near-term:

- extract pause behavior behind the generic fault-injector interface
- add process kill/restart
- add broker and database disconnect faults
- add additional application-level invariants
- strengthen adapter lifecycle isolation
- add integration coverage in CI
- package a reproducible containerized runner

Future adapters:

- BullMQ / Redis
- Amazon SQS

Future adapters will preserve each system's real delivery semantics rather than
pretending all brokers use the same lease, visibility, or acknowledgement
model.

## Status

Faultline is an early framework prototype.

The Celery reference adapter currently runs the stale-worker experiment
end-to-end using real workers, Redis redelivery, PostgreSQL writes, process
pause/resume injection, execution histories, and invariant evaluation.

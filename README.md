# Faultline

**Correctness testing for at-least-once background workers.**

Faultline injects real failures into queue consumers, records execution
histories, and checks whether application-level side-effect invariants survive
redelivery and stale-worker recovery.

The current reference integration uses:

- Celery
- Redis
- PostgreSQL
- Docker
- real worker processes
- `SIGSTOP` / `SIGCONT`
- visibility-timeout redelivery
- fencing tokens
- machine-readable execution histories

## The bug Faultline reproduces

At-least-once workers can execute the same logical job more than once.

A worker can begin processing a job, lose progress or connectivity long enough
for ownership to expire, and later resume after another worker has already
taken over.

Without a commit-time ownership check:

```text
Worker A receives payment-42
token = 1
        |
        v
Worker A reaches commit window
        |
        v
FAULT: SIGSTOP
        |
        v
visibility timeout expires
        |
        v
Worker B receives redelivery
token = 2
        |
        v
Worker B commits
        |
        v
FAULT RECOVERY: SIGCONT
        |
        v
Worker A resumes with stale token 1
        |
        v
Worker A also commits
Result:

committed effects = 1
stale rejections = 1
AT_MOST_ONE_EFFECT = PASS
Run the comparison

Requirements:

Python 3.11+
Docker
Docker Compose

Install locally:

python3 -m venv .framework-venv
source .framework-venv/bin/activate
python -m pip install -e '.[dev]'

Run the complete experiment:

faultline compare \
  --adapter celery \
  --fault pause \
  --invariant at-most-one-effect

Expected result:

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

The comparison returns exit code 0 only when Faultline successfully observes
the expected contrast:

unsafe implementation -> invariant violation
fenced implementation -> invariant preserved
Run one implementation

Unsafe:

faultline test \
  --adapter celery \
  --fault pause \
  --implementation unsafe \
  --invariant at-most-one-effect

Expected:

Committed effects:       2
Stale rejections:        0
Current fencing token:   2

AT_MOST_ONE_EFFECT: FAIL

The command returns exit code 1 because the invariant was violated.

Fenced:

faultline test \
  --adapter celery \
  --fault pause \
  --implementation fenced \
  --invariant at-most-one-effect

Expected:

Committed effects:       1
Stale rejections:        1
Current fencing token:   2

AT_MOST_ONE_EFFECT: PASS

The command returns exit code 0.

What Faultline actually does

The Celery adapter runs two real workers against Redis and PostgreSQL.

                         Faultline CLI
                              |
                              v
                         Orchestrator
                              |
              +---------------+---------------+
              |                               |
              v                               v
        Fault Injector                   Celery Adapter
       SIGSTOP/SIGCONT                         |
              |                               v
              |                         Redis Broker
              |                               |
              +-----------> Worker A          |
                              |                |
                              |            redelivery
                              |                |
                              +-----------> Worker B
                                               |
                                               v
                                        PostgreSQL
                                       effect ledger
                                               |
                         +---------------------+--------------------+
                         |                                          |
                         v                                          v
                 Execution History                          Invariant Checker
                  history.jsonl                           at-most-one-effect
                         |                                          |
                         +------------------+-----------------------+
                                            |
                                            v
                                        report.json

The experiment intentionally creates this sequence:

1. Worker A receives the task and receives fencing token 1.
2. Worker A reaches the dangerous pre-commit window.
3. Faultline stops Worker A with SIGSTOP.
4. The Redis visibility timeout expires.
5. Worker B receives the redelivered task and receives token 2.
6. Worker B commits the application effect.
7. Faultline resumes Worker A with SIGCONT.
8. Worker A attempts to finish its original execution.
9. Faultline checks the resulting PostgreSQL history.

The only difference between the two reference implementations is how the final
side effect is committed.

Unsafe commit

The worker writes its effect without validating that it still owns the job.

token 1 -> accepted even though current token = 2

Both workers therefore commit.

Fenced commit

The authoritative PostgreSQL state is checked inside the commit path.

presented token = 1
current token   = 2

The stale worker is rejected before its effect is committed.

The invariant

The first supported invariant is:

AT_MOST_ONE_EFFECT

For every logical job:

committed_effects(job_id) <= 1

This is deliberately narrower than claiming universal "exactly once"
execution.

Faultline currently checks an observable application-side effect stored in its
PostgreSQL ledger.

Execution histories

Every run emits a chronological JSONL history.

Example fenced history:

worker-a  token=1  delivery_started
worker-a  token=1  ready_to_commit

FAULT                 SIGSTOP worker-a

worker-b  token=2  delivery_started
worker-b  token=2  commit_accepted

ownership observed    token=2

FAULT RECOVERY        SIGCONT worker-a

worker-a  token=1  commit_rejected

Artifacts are written beneath:

artifacts/runs/

Each run contains:

history.jsonl
report.json
worker-a.log
worker-b.log

Example report fields:

{
  "framework": "faultline",
  "adapter": "celery",
  "implementation": "fenced",
  "fault": "pause",
  "invariant": "at-most-one-effect",
  "committed_effects": 1,
  "current_fencing_token": 2,
  "result": "PASS"
}

The actual report currently uses the mode field for the implementation name;
the public CLI exposes --implementation while retaining --mode as a
backward-compatible alias.

Why fencing is necessary

A lease or visibility timeout answers:

Who is allowed to own the work now?

It does not automatically prevent a previous owner from waking up later and
writing stale state.

Faultline assigns a monotonically increasing token on every ownership
transition:

Worker A -> token 1
Worker B -> token 2

A commit is accepted only when:

presented_token == current_token

Therefore:

Worker B: 2 == 2 -> commit accepted
Worker A: 1 != 2 -> stale commit rejected

The authoritative storage system performs the check. Correctness does not rely
on Worker A realizing that its lease expired while it was paused.

Current capabilities
Adapter
Celery + Redis
Real fault
pause -> SIGSTOP
recovery -> SIGCONT
Recovery mechanism
Redis visibility-timeout redelivery
Side-effect store
PostgreSQL
Invariant
at-most-one-effect
Implementations
unsafe
fenced
Outputs
terminal verdict
exit code
history.jsonl
report.json
worker logs
Project structure
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
│
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
│
├── tests/
│   ├── test_framework_cleanup.py
│   ├── test_framework_cli.py
│   ├── test_framework_invariants.py
│   └── test_framework_reports.py
│
├── artifacts/
│   └── runs/
│
├── pyproject.toml
└── SCOPE_FRAMEWORK.md
Testing

Install development dependencies:

python -m pip install -e '.[dev]'

Run framework tests:

python -m pytest \
  tests/test_framework_invariants.py \
  tests/test_framework_reports.py \
  tests/test_framework_cleanup.py \
  tests/test_framework_cli.py \
  -q

The current framework regression suite covers:

invariant semantics
canonical unsafe evidence
canonical fenced evidence
stale-token rejection evidence
CLI parsing
backward-compatible CLI arguments
best-effort worker recovery
Methodology

Faultline is Jepsen-inspired in methodology:

drive a real system
-> inject a real failure
-> collect an execution history
-> check an explicit correctness property

Faultline is not Jepsen and does not claim equivalent coverage or formal
linearizability verification.

What Faultline does not claim

Faultline does not currently claim:

universal exactly-once execution
formal proof of linearizability
Byzantine fault tolerance
consensus verification
production certification for Celery or Redis
exhaustive fault coverage
correctness of arbitrary external side effects

The current result is deliberately specific:

Under the included Celery/Redis/PostgreSQL stale-worker experiment, the
unsafe reference implementation produces two committed effects after
redelivery, while commit-time fencing rejects the stale worker and preserves
the at-most-one-effect invariant.

Roadmap

Near-term work:

extract process pause into the generic fault-injector interface
add process kill/restart
add broker-disconnect faults
add database-disconnect faults
add additional history-based invariants
improve adapter lifecycle isolation
add deterministic integration tests
publish a Docker image
add CI integration

Future adapters:

BullMQ / Redis
Amazon SQS

Adapters will preserve each system's actual delivery semantics rather than
pretending all queue systems have the same lease or acknowledgement model.

Status

Faultline is currently an early framework prototype.

The Celery reference adapter already runs the complete stale-worker experiment
end-to-end and emits reproducible machine-readable evidence for both the unsafe
and fenced implementations.

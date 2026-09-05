# Faultline — Correctness Testing for At-Least-Once Workers

Faultline is a failure-testing framework for background workers and queue consumers.

It drives real worker integrations, injects failures, records execution histories,
and checks application-level correctness invariants after recovery.

## Core responsibilities

Faultline has six core concepts:

1. Adapters
   - connect Faultline to real worker/queue systems

2. Fault injectors
   - pause processes
   - kill processes
   - disrupt dependencies
   - trigger redelivery/recovery conditions

3. History recorder
   - record deliveries
   - ownership changes
   - effects
   - faults
   - retries
   - stale commit attempts

4. Effect ledger
   - record observable application effects

5. Invariant checkers
   - at-most-one-effect
   - stale-owner-cannot-commit
   - no-lost-committed-effect
   - eventually-processed-after-recovery

6. Reports
   - human-readable timeline
   - machine-readable JSON/JSONL
   - PASS/FAIL evidence

## First milestone

Reproduce a duplicate side effect in a real Celery worker using:

- Celery
- Redis
- PostgreSQL
- late acknowledgement
- SIGSTOP / process pause
- visibility expiry / redelivery
- a second worker

Then run the same workload with fencing-token validation and demonstrate:

UNSAFE:
- committed effects = 2
- at-most-one-effect = FAIL

FENCED:
- committed effects = 1
- stale commit attempts = 1
- stale commits accepted = 0
- at-most-one-effect = PASS

## Non-goals

Faultline does not claim:

- universal exactly-once execution
- formal proof of linearizability
- Byzantine fault tolerance
- Jepsen equivalence

The methodology is Jepsen-inspired:
inject real failures, record histories, and check explicit invariants.

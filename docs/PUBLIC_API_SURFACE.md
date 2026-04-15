# Public API Surface

Faultline is intended to be used as a correctness-oriented execution primitive.

## Core contracts

- `submit(job_payload, idempotency_key?)`
- `claim(worker_id, batch_size)`
- `complete(job_id, fencing_token, result)`
- `fail(job_id, fencing_token, reason)`
- `reconcile()`

## Worker contract

A worker may execute stale work.

A worker may not commit stale work.

Commit validity is enforced at the database boundary.

## Retry semantics

Retries are explicit:
- bounded by retry policy
- re-enter queue through `next_run_at`
- remain protected by fencing checks across reclaims and retries

## Idempotency expectations

Faultline protects the fenced commit path.
External side effects still require:
- idempotency keys
- outbox-style wrapping
- replay-aware operator workflow


Database Consistency Notes
Correctness invariant

A worker may execute stale work, but it may not commit stale work.

Faultline enforces this with:

submitted_fencing_token == current_database_fencing_token
Retry behavior

Retries must not reuse stale fencing tokens after ownership changes.

Idempotency

Idempotency keys protect duplicate submission paths. Fencing tokens protect stale-worker commit paths.

Availability note

When PostgreSQL is unreachable, Faultline should fail closed or retry rather than accept commits without validation.

"""
worker/leases.py
─────────────────
Lease acquisition semantics for Faultline.

This module documents and re-exports the core lease coordination primitives
implemented in services/worker/worker.py. It exists as an architectural
reference for the lease ownership model.

Lease Ownership Model
─────────────────────
A lease is a time-bound claim on a job row. It has three components:

    lease_owner       TEXT      — the worker UUID holding the lease
    lease_expires_at  TIMESTAMPTZ — when the lease expires if not renewed
    fencing_token     BIGINT    — monotonically increasing epoch counter

Each time a worker acquires a lease, fencing_token is incremented atomically:

    UPDATE jobs
    SET lease_owner      = <worker_id>,
        lease_expires_at = NOW() + INTERVAL '<n> seconds',
        fencing_token    = fencing_token + 1,
        state            = 'running'
    WHERE id = <job_id>
      AND (state = 'queued' OR (state = 'running' AND lease_expires_at < NOW()))
    RETURNING id, fencing_token

This single UPDATE is the epoch advance. No separate read-then-write exists,
so there is no window for two workers to read the same token value.

Fencing Token Invariant
───────────────────────
Any write that carries an outdated fencing_token is provably stale:

    - Worker A claims job → token = 1
    - Worker A's lease expires
    - Worker B claims job → token = 2
    - Worker A wakes up and calls assert_fence(token=1)
      → current token is 2 → stale_write_blocked → transaction aborted

This invariant holds at the database boundary, not just in application code.

Concurrent Claim Safety
───────────────────────
The production claim path uses FOR UPDATE SKIP LOCKED:

    SELECT id FROM jobs
    WHERE state = 'queued'
    FOR UPDATE SKIP LOCKED
    LIMIT 1

This ensures:
    - Multiple workers never block each other on the same row
    - Each row is claimed by exactly one worker per loop iteration
    - No thundering herd: workers skip locked rows immediately

Crash Recovery
──────────────
When a worker crashes mid-execution, its lease expires naturally. The
next worker that polls will see the expired lease and reclaim the job
with a new fencing token. The crashed worker's uncommitted state is
rolled back automatically by PostgreSQL.

The reconciler (services/worker/reconciler.py) handles the complementary
case: a worker that committed the ledger entry but crashed before updating
job state. It converges state by joining jobs to ledger_entries.
"""

# Lease duration default — overridden by LEASE_SECONDS env var in worker.py.
# Should be set to at least 2× the p99 execution time of the slowest job type.
DEFAULT_LEASE_SECONDS = 30

# The barrier table name used for deterministic concurrency testing.
BARRIER_TABLE = "barriers"

# Stale error codes raised by assert_fence() and mark_succeeded().
# These are expected under normal race conditions and should not be
# treated as fatal errors — they indicate correct stale-write rejection.
STALE_ERROR_CODES = frozenset({"stale_token", "lease_expired", "stale_commit"})
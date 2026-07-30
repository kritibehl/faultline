# Database Schema and Correctness Invariants

## Scope

Faultline does not claim universal exactly-once execution.

The implemented and tested guarantees are:

- duplicate commit prevention
- idempotent effect handling
- transactional event publication
- stale-worker rejection
- tested recovery invariants

## Core schema

A simplified representation of the correctness-critical tables:

```sql
CREATE TABLE jobs (
    job_id UUID PRIMARY KEY,
    state TEXT NOT NULL,
    lease_owner TEXT,
    lease_expires_at TIMESTAMPTZ,
    fencing_token BIGINT NOT NULL DEFAULT 0,
    committed_at TIMESTAMPTZ
);

CREATE TABLE job_results (
    job_id UUID PRIMARY KEY REFERENCES jobs(job_id),
    fencing_token BIGINT NOT NULL,
    result_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE outbox_events (
    event_id UUID PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES jobs(job_id),
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    published_at TIMESTAMPTZ,
    UNIQUE (job_id, event_type)
);

CREATE TABLE delivered_effects (
    idempotency_key TEXT PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES jobs(job_id),
    delivered_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
Guarantee mapping
Row locking

Row-level locking serializes competing lease-acquisition and state-transition attempts for the same job.

It prevents two workers from simultaneously updating the same ownership record based on an identical database state.

Row locking alone does not protect against a worker that pauses, loses its lease, and later resumes.

Fencing tokens

Every successful lease acquisition receives a monotonically increasing token.

Commit validation requires the presented token to equal the job's current token.

A worker holding token 7 cannot commit after another worker acquires token 8.

This provides stale-worker rejection even when the old worker reconnects after lease expiry.

Unique constraints

Unique constraints enforce one accepted result and prevent duplicate event identities at the database boundary.

Examples:

one result row per job
one logical outbox event per job and event type
one delivery record per idempotency key

These constraints provide a final database-enforced defense against duplicate persistence.

Idempotency keys

An idempotency key identifies a logical external effect.

A repeated delivery checks or inserts the same key and becomes a no-op when the key already exists.

This provides idempotent effect handling; it does not imply that the transport delivers a message only once.

Transactions

The accepted job-state transition, result record, and outbox event are persisted within one database transaction.

The transaction either commits all correctness-critical records or commits none of them.

This prevents a completed job from being stored without its corresponding publication record.

Transactional outbox guarantee

The outbox provides transactional event publication:

validate the current fencing token;
persist the accepted result;
update the job state;
insert the outbox event;
commit the transaction.

A separate publisher may retry event delivery.

Repeated delivery is handled through idempotency keys or unique event identity.

Precise language

Avoid:

Faultline guarantees exactly-once execution.

Prefer:

Faultline prevents duplicate commits through fencing-token validation and database constraints, publishes accepted state transitions through a transactional outbox, and suppresses repeated effects using idempotency keys.

Tested recovery invariants

The deterministic correctness demo verifies:

a stale worker cannot commit after lease takeover;
the current lease owner can commit;
a second commit for the same job is rejected;
every accepted commit produces one outbox event;
repeated effect delivery is suppressed;
recovery scenarios complete with zero duplicate commits and zero lost outbox events.

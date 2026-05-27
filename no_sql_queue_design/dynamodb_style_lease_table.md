# DynamoDB-Style Lease Table Design

Safe claim: this is a DynamoDB-style design artifact, not a deployed DynamoDB implementation.

## Table shape

| Field | Purpose |
|---|---|
| job_id | partition key |
| lease_owner | current worker |
| lease_expires_at | reclaim boundary |
| fencing_token | monotonic ownership version |
| state | queued/running/succeeded/failed |
| updated_at | operational debugging |

## Conditional write model

A worker commit would require a condition equivalent to:

```text
submitted_fencing_token == current_fencing_token
Why this matters

DynamoDB-style conditional writes can model the same stale-write rejection pattern as PostgreSQL row locking.

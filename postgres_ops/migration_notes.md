# Faultline PostgreSQL Migration Notes

## Migration principles

- never remove fencing-token columns without a compatibility plan
- preserve commit-log uniqueness guarantees
- add indexes before increasing worker concurrency
- avoid long-running blocking migrations on hot job tables

## Important columns

| Table | Column | Purpose |
|---|---|---|
| jobs | state | queued/running/succeeded/failed lifecycle |
| jobs | lease_owner | current worker owner |
| jobs | lease_expires_at | reclaim boundary |
| jobs | fencing_token | monotonic commit authority |
| ledger_entries | job_id | protected commit identity |
| ledger_entries | fencing_token | commit epoch |

## Recommended indexes

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jobs_state_next_run
ON jobs(state, next_run_at);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jobs_lease_expiry
ON jobs(state, lease_expires_at);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ledger_job
ON ledger_entries(job_id);
Migration safety checklist
run replay validation after migration
run duplicate-rate benchmark after migration
verify stale-write rejection still works
verify reconciler can converge partial failures
verify /metrics endpoint still exports stale-write and lease-takeover counters

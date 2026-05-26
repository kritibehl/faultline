
Slow Query and EXPLAIN ANALYZE Notes
Claim path
EXPLAIN ANALYZE
SELECT id
FROM jobs
WHERE state = 'queued'
   OR (state = 'running' AND lease_expires_at < NOW())
ORDER BY updated_at NULLS FIRST
LIMIT 1
FOR UPDATE SKIP LOCKED;
Commit validation path
EXPLAIN ANALYZE
SELECT fencing_token
FROM jobs
WHERE id = 'job-id'
FOR UPDATE;
Indexes to verify
CREATE INDEX IF NOT EXISTS idx_jobs_state_next_run
ON jobs(state, next_run_at);

CREATE INDEX IF NOT EXISTS idx_jobs_lease_expiry
ON jobs(state, lease_expires_at);

CREATE INDEX IF NOT EXISTS idx_ledger_entries_job
ON ledger_entries(job_id);
What to look for
sequential scans on hot job tables
high lock wait time
slow claim latency
slow commit validation
repeated retry pressure
Safe claim

These notes document PostgreSQL reliability diagnostics for Faultline. They do not claim production database tuning.

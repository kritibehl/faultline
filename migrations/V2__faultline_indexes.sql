CREATE INDEX IF NOT EXISTS idx_jobs_state_next_run
ON jobs(state, next_run_at);

CREATE INDEX IF NOT EXISTS idx_jobs_lease_expiry
ON jobs(state, lease_expires_at);

CREATE INDEX IF NOT EXISTS idx_ledger_entries_job
ON ledger_entries(job_id);

-- 003_add_next_run_at.sql
ALTER TABLE jobs
  ADD COLUMN IF NOT EXISTS next_run_at timestamp;

-- If 003 also creates an index, make it idempotent too (example):
CREATE INDEX IF NOT EXISTS idx_jobs_next_run_at
  ON jobs(next_run_at);

ALTER TABLE jobs
  ADD COLUMN IF NOT EXISTS next_run_at timestamp without time zone;

CREATE INDEX IF NOT EXISTS idx_jobs_next_run_at
  ON jobs(next_run_at);

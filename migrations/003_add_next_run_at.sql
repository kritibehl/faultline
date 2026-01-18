ALTER TABLE jobs
ADD COLUMN next_run_at TIMESTAMP;

CREATE INDEX idx_jobs_next_run_at ON jobs(next_run_at);

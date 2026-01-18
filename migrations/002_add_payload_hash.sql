ALTER TABLE jobs
ADD COLUMN payload_hash TEXT NOT NULL;

CREATE INDEX idx_jobs_idempotency_key ON jobs(idempotency_key);

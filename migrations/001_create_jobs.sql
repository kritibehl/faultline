ALTER TABLE jobs
  ADD COLUMN IF NOT EXISTS payload_hash text;

CREATE INDEX IF NOT EXISTS idx_jobs_payload_hash
  ON jobs(payload_hash);

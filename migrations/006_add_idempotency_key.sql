-- 006_add_idempotency_key.sql
ALTER TABLE jobs
  ADD COLUMN IF NOT EXISTS idempotency_key TEXT;

-- Enforce dedupe across submissions (optional but strongly recommended)
CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_idempotency_key
  ON jobs(idempotency_key)
  WHERE idempotency_key IS NOT NULL;

-- 013_add_retry_columns.sql
-- Adds last_error column for storing failure messages on retry/failure.
-- Ensures attempts column has correct default if not already set.

ALTER TABLE jobs
  ADD COLUMN IF NOT EXISTS last_error TEXT;

-- Ensure attempts has a default (safe no-op if already correct)
ALTER TABLE jobs
  ALTER COLUMN attempts SET DEFAULT 0;

-- Extend state check to include 'failed' if not already present
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'ck_jobs_state'
  ) THEN
    ALTER TABLE jobs DROP CONSTRAINT ck_jobs_state;
  END IF;
END $$;

ALTER TABLE jobs
  ADD CONSTRAINT ck_jobs_state
  CHECK (state IN ('queued', 'running', 'succeeded', 'failed'));
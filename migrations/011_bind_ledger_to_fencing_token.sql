-- 011_bind_ledger_to_fencing_token.sql
BEGIN;

-- 1) Add token column
ALTER TABLE ledger_entries
  ADD COLUMN IF NOT EXISTS fencing_token BIGINT NOT NULL DEFAULT 0;

-- 2) Drop old uniqueness on job_id if it exists (may be an index or constraint)
DO $$
BEGIN
  -- constraint form
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ledger_entries_job_id_key') THEN
    ALTER TABLE ledger_entries DROP CONSTRAINT ledger_entries_job_id_key;
  END IF;
EXCEPTION WHEN undefined_object THEN
  NULL;
END $$;

DROP INDEX IF EXISTS uq_ledger_entries_job_id;
DROP INDEX IF EXISTS ledger_entries_job_id_key;

-- 3) New uniqueness: (job_id, fencing_token)
CREATE UNIQUE INDEX IF NOT EXISTS uq_ledger_entries_job_fence
  ON ledger_entries(job_id, fencing_token);

COMMIT;
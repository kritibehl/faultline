-- 005_add_jobs_state_check.sql
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'ck_jobs_state'
  ) THEN
    ALTER TABLE jobs
      ADD CONSTRAINT ck_jobs_state
      CHECK (state IN ('queued','running','succeeded','failed'));
  END IF;
END $$;
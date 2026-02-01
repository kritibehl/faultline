-- 005_add_jobs_state_check.sql
-- Enforce legal job lifecycle states

ALTER TABLE jobs
  ADD CONSTRAINT IF NOT EXISTS ck_jobs_state
  CHECK (state IN ('queued','running','succeeded','failed'));

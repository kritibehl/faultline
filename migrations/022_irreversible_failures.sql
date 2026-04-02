ALTER TABLE jobs
ADD COLUMN IF NOT EXISTS first_irreversible_failure_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS first_irreversible_failure_reason TEXT;

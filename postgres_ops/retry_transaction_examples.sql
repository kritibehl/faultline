-- Faultline retryable transaction examples.
-- These examples are documentation artifacts for operational reasoning.

-- Example 1: retry-safe claim path
BEGIN;

WITH candidate AS (
  SELECT id
  FROM jobs
  WHERE state = 'queued'
     OR (state = 'running' AND lease_expires_at < NOW())
  ORDER BY updated_at NULLS FIRST
  LIMIT 1
  FOR UPDATE SKIP LOCKED
)
UPDATE jobs
SET state = 'running',
    lease_owner = 'worker-a',
    lease_expires_at = NOW() + INTERVAL '30 seconds',
    fencing_token = fencing_token + 1,
    updated_at = NOW()
WHERE id IN (SELECT id FROM candidate)
RETURNING id, fencing_token;

COMMIT;

-- If serialization/deadlock errors occur:
-- 1. rollback
-- 2. backoff with jitter
-- 3. retry claim transaction
-- 4. do not reuse stale fencing token after retry


-- Example 2: commit validation path
BEGIN;

SELECT fencing_token
FROM jobs
WHERE id = 'job-id'
FOR UPDATE;

-- Application validates submitted_fencing_token == current fencing_token.
-- If token is stale, rollback and emit stale-write rejection.

INSERT INTO ledger_entries(job_id, fencing_token)
VALUES ('job-id', 42)
ON CONFLICT DO NOTHING;

UPDATE jobs
SET state = 'succeeded',
    lease_owner = NULL,
    lease_expires_at = NULL,
    updated_at = NOW()
WHERE id = 'job-id';

COMMIT;

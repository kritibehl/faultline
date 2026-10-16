CREATE TABLE IF NOT EXISTS job_ownership (
    job_id TEXT PRIMARY KEY,
    current_token BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS attempts (
    id BIGSERIAL PRIMARY KEY,
    job_id TEXT NOT NULL,
    worker_name TEXT NOT NULL,
    fencing_token BIGINT NOT NULL,
    phase TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS effects (
    id BIGSERIAL PRIMARY KEY,
    job_id TEXT NOT NULL,
    worker_name TEXT NOT NULL,
    fencing_token BIGINT NOT NULL,
    amount INTEGER NOT NULL,
    idempotency_key TEXT,
    committed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS stale_rejections (
    id BIGSERIAL PRIMARY KEY,
    job_id TEXT NOT NULL,
    worker_name TEXT NOT NULL,
    presented_token BIGINT NOT NULL,
    current_token BIGINT NOT NULL,
    rejected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_attempts_job
ON attempts(job_id);

CREATE INDEX IF NOT EXISTS idx_effects_job
ON effects(job_id);

CREATE INDEX IF NOT EXISTS idx_rejections_job
ON stale_rejections(job_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_effects_idempotency_key
ON effects(idempotency_key)
WHERE idempotency_key IS NOT NULL;


-- Milestone 8: snapshot the authoritative ownership token at side-effect
-- insertion time. A SHARE lock conflicts with concurrent token UPDATEs.
-- That lock is retained until the inserting transaction completes, making
-- the snapshot/commit order serializable with ownership transitions.
-- The attempt timeline alone is NOT authoritative for this property.
ALTER TABLE effects
    ADD COLUMN IF NOT EXISTS owner_token_at_commit BIGINT;

CREATE OR REPLACE FUNCTION faultline_stamp_effect_owner()
RETURNS TRIGGER AS $$
BEGIN
    SELECT current_token
      INTO NEW.owner_token_at_commit
      FROM job_ownership
     WHERE job_id = NEW.job_id
       FOR SHARE;

    -- A missing ownership row produces NULL evidence: the auditor must
    -- report INCONCLUSIVE rather than claiming a safe commit.
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS faultline_effect_owner_snapshot ON effects;
CREATE TRIGGER faultline_effect_owner_snapshot
BEFORE INSERT ON effects
FOR EACH ROW
EXECUTE FUNCTION faultline_stamp_effect_owner();

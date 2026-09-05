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

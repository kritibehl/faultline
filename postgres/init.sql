CREATE TABLE IF NOT EXISTS demo_workers (
    worker_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'idle',
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS demo_jobs (
    job_id TEXT PRIMARY KEY,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    state TEXT NOT NULL DEFAULT 'queued',
    lease_owner TEXT,
    lease_expires_at TIMESTAMPTZ,
    fencing_token BIGINT NOT NULL DEFAULT 0,
    attempts INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS demo_commit_log (
    commit_id BIGSERIAL PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES demo_jobs(job_id),
    worker_id TEXT NOT NULL,
    fencing_token BIGINT NOT NULL,
    result JSONB NOT NULL DEFAULT '{}'::jsonb,
    committed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(job_id)
);

CREATE INDEX IF NOT EXISTS idx_demo_jobs_state ON demo_jobs(state);
CREATE INDEX IF NOT EXISTS idx_demo_jobs_lease ON demo_jobs(lease_expires_at);
CREATE INDEX IF NOT EXISTS idx_demo_commit_log_job ON demo_commit_log(job_id);

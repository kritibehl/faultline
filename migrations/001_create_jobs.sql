CREATE TABLE jobs (
    id UUID PRIMARY KEY,
    idempotency_key TEXT UNIQUE,
    state TEXT NOT NULL,
    payload JSONB NOT NULL,

    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    last_error TEXT,

    lease_owner TEXT,
    lease_expires_at TIMESTAMP,

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_jobs_state ON jobs(state);
CREATE INDEX idx_jobs_lease_expires ON jobs(lease_expires_at);

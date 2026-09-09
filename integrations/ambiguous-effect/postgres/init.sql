CREATE TABLE charges (
    id BIGSERIAL PRIMARY KEY,
    job_id TEXT NOT NULL,
    worker_name TEXT NOT NULL,
    fencing_token BIGINT NOT NULL,
    amount INTEGER NOT NULL,
    idempotency_key TEXT,
    committed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_charges_job_id
    ON charges(job_id);

CREATE UNIQUE INDEX idx_charges_idempotency_key
    ON charges(idempotency_key)
    WHERE idempotency_key IS NOT NULL;


CREATE TABLE remote_ownership (
    job_id TEXT PRIMARY KEY,
    current_token BIGINT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE TABLE service_events (
    id BIGSERIAL PRIMARY KEY,
    job_id TEXT NOT NULL,
    worker_name TEXT,
    fencing_token BIGINT,
    event_type TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_service_events_job
    ON service_events(job_id, created_at, id);

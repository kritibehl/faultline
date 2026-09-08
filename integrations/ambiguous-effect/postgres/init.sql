CREATE TABLE charges (
    id BIGSERIAL PRIMARY KEY,
    job_id TEXT NOT NULL,
    amount INTEGER NOT NULL,
    idempotency_key TEXT,
    committed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_charges_job_id
    ON charges(job_id);

CREATE UNIQUE INDEX idx_charges_idempotency_key
    ON charges(idempotency_key)
    WHERE idempotency_key IS NOT NULL;

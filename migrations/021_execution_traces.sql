CREATE TABLE IF NOT EXISTS execution_traces (
    id UUID PRIMARY KEY,
    job_id UUID NOT NULL,
    workflow_run_id UUID,
    event_type TEXT NOT NULL,
    step_name TEXT,
    fencing_token BIGINT,
    lease_owner TEXT,
    details JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

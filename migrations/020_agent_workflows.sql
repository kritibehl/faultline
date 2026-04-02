CREATE TABLE IF NOT EXISTS workflow_runs (
    id UUID PRIMARY KEY,
    job_id UUID NOT NULL,
    workflow_type TEXT NOT NULL,
    state TEXT NOT NULL,
    current_step TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS workflow_steps (
    id UUID PRIMARY KEY,
    workflow_run_id UUID NOT NULL,
    step_index INT NOT NULL,
    step_name TEXT NOT NULL,
    state TEXT NOT NULL,
    attempt INT NOT NULL DEFAULT 0,
    failure_class TEXT,
    retry_reason TEXT,
    fallback_step TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    output_json JSONB,
    UNIQUE(workflow_run_id, step_index)
);

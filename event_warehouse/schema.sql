CREATE TABLE IF NOT EXISTS dim_services (
  service_id TEXT PRIMARY KEY,
  service_name TEXT NOT NULL,
  service_tier TEXT NOT NULL,
  owner_team TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fact_events (
  event_id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL,
  service_id TEXT NOT NULL REFERENCES dim_services(service_id),
  event_type TEXT NOT NULL,
  occurred_at TIMESTAMP NOT NULL,
  fencing_token INTEGER,
  duplicate_commit BOOLEAN NOT NULL DEFAULT FALSE,
  stale_write_rejected BOOLEAN NOT NULL DEFAULT FALSE,
  retry_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS fact_failures (
  failure_id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL,
  service_id TEXT NOT NULL REFERENCES dim_services(service_id),
  failure_type TEXT NOT NULL,
  detected_at TIMESTAMP NOT NULL,
  recovered_at TIMESTAMP,
  recovery_time_ms INTEGER,
  customer_impact INTEGER NOT NULL DEFAULT 0,
  severity TEXT NOT NULL
);

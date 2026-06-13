INSERT INTO dim_services (service_id, service_name, service_tier, owner_team) VALUES
  ('svc_queue', 'queue_runtime', 'critical', 'platform'),
  ('svc_worker', 'worker_service', 'critical', 'backend'),
  ('svc_db', 'postgres', 'critical', 'data'),
  ('svc_outbox', 'outbox', 'high', 'platform')
ON CONFLICT DO NOTHING;

INSERT INTO fact_events (
  event_id, job_id, service_id, event_type, occurred_at,
  fencing_token, duplicate_commit, stale_write_rejected, retry_count
) VALUES
  ('evt_001', 'job_1', 'svc_worker', 'job.claimed', '2026-06-01 10:00:00', 1, false, false, 0),
  ('evt_002', 'job_1', 'svc_db', 'job.completed', '2026-06-01 10:00:10', 2, false, false, 0),
  ('evt_003', 'job_1', 'svc_db', 'stale_write.rejected', '2026-06-01 10:00:14', 1, false, true, 0),
  ('evt_004', 'job_2', 'svc_worker', 'job.retried', '2026-06-01 10:01:00', 1, false, false, 2),
  ('evt_005', 'job_3', 'svc_db', 'duplicate_commit.blocked', '2026-06-01 10:02:00', 3, false, true, 1)
ON CONFLICT DO NOTHING;

INSERT INTO fact_failures (
  failure_id, job_id, service_id, failure_type, detected_at,
  recovered_at, recovery_time_ms, customer_impact, severity
) VALUES
  ('fail_001', 'job_1', 'svc_worker', 'stale_worker_late_commit', '2026-06-01 10:00:08', '2026-06-01 10:00:26', 18000, 120, 'sev3'),
  ('fail_002', 'job_2', 'svc_queue', 'retry_storm', '2026-06-01 10:01:00', '2026-06-01 10:01:42', 42000, 1832, 'sev2'),
  ('fail_003', 'job_3', 'svc_outbox', 'partial_write_recovery', '2026-06-01 10:02:00', '2026-06-01 10:02:18', 18000, 54, 'sev3')
ON CONFLICT DO NOTHING;

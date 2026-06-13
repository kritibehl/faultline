SELECT
  COUNT(*) AS total_events,
  SUM(CASE WHEN stale_write_rejected THEN 1 ELSE 0 END) AS stale_writes_rejected,
  ROUND(
    100.0 * SUM(CASE WHEN stale_write_rejected THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
    2
  ) AS stale_write_rejection_rate_percent
FROM fact_events;

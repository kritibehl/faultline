SELECT
  COUNT(*) AS total_events,
  SUM(CASE WHEN duplicate_commit THEN 1 ELSE 0 END) AS duplicate_commits,
  ROUND(
    100.0 * SUM(CASE WHEN duplicate_commit THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
    2
  ) AS duplicate_rate_percent
FROM fact_events;

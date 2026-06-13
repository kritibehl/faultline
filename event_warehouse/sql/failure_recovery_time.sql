SELECT
  failure_type,
  COUNT(*) AS failure_count,
  ROUND(AVG(recovery_time_ms), 2) AS avg_recovery_time_ms,
  MAX(recovery_time_ms) AS max_recovery_time_ms,
  SUM(customer_impact) AS total_customer_impact
FROM fact_failures
GROUP BY failure_type
ORDER BY avg_recovery_time_ms DESC;

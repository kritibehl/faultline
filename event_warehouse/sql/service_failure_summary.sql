SELECT
  s.service_name,
  s.owner_team,
  COUNT(f.failure_id) AS failure_count,
  ROUND(AVG(f.recovery_time_ms), 2) AS avg_recovery_time_ms,
  SUM(f.customer_impact) AS customer_impact
FROM fact_failures f
JOIN dim_services s ON f.service_id = s.service_id
GROUP BY s.service_name, s.owner_team
ORDER BY customer_impact DESC;

# PostgreSQL Lock Contention Runbook

## Symptoms

- claim latency rises
- commit latency rises
- retries increase
- pool pressure increases

## Diagnostic SQL

```sql
SELECT state, count(*)
FROM pg_stat_activity
GROUP BY state;
SELECT relation::regclass, mode, granted, count(*)
FROM pg_locks
GROUP BY relation, mode, granted;
Mitigation
reduce worker concurrency
increase batch size carefully
verify lease-expiry indexes
tune retry backoff
inspect long-running transactions

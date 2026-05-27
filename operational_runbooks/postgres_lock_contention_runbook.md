# PostgreSQL Lock Contention Runbook

## Symptoms

- claim latency rises
- commit latency rises
- active DB connections increase
- retry queue grows
- worker throughput drops

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
inspect long-running transactions
verify lease-expiry indexes
tune retry backoff
increase batch size carefully

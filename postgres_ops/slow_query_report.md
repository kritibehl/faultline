# PostgreSQL Slow Query and Lock Diagnostics

Faultline uses PostgreSQL as the correctness boundary for lease ownership and fencing-token commit validation.

## Diagnostic goals

- detect slow claim/update paths
- identify lock contention around lease ownership
- inspect retryable transaction failures
- understand connection pool pressure

## Example slow-query areas

| Query path | Risk | Diagnostic signal |
|---|---|---|
| job claim | contention under high worker count | increased claim latency |
| commit validation | row lock wait | commit latency spike |
| lease reclaim | expired lease scan | slow recovery |
| reconciler sweep | table scan risk | background load increase |

## Slow-query check

```sql
SELECT query, calls, total_exec_time, mean_exec_time
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;
Lock contention check
SELECT
  blocked.pid AS blocked_pid,
  blocked.query AS blocked_query,
  blocking.pid AS blocking_pid,
  blocking.query AS blocking_query
FROM pg_stat_activity blocked
JOIN pg_locks blocked_locks
  ON blocked_locks.pid = blocked.pid
JOIN pg_locks blocking_locks
  ON blocking_locks.locktype = blocked_locks.locktype
 AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database
 AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
 AND blocking_locks.page IS NOT DISTINCT FROM blocked_locks.page
 AND blocking_locks.tuple IS NOT DISTINCT FROM blocked_locks.tuple
 AND blocking_locks.transactionid IS NOT DISTINCT FROM blocked_locks.transactionid
 AND blocking_locks.classid IS NOT DISTINCT FROM blocked_locks.classid
 AND blocking_locks.objid IS NOT DISTINCT FROM blocked_locks.objid
 AND blocking_locks.objsubid IS NOT DISTINCT FROM blocked_locks.objsubid
JOIN pg_stat_activity blocking
  ON blocking.pid = blocking_locks.pid
WHERE NOT blocked_locks.granted
  AND blocking_locks.granted;
Operational interpretation

Faultline intentionally spends coordination overhead to enforce correctness at the commit boundary. Slow-query and lock diagnostics help operators tune batch size, lease duration, polling interval, and transaction retry behavior.


PostgreSQL Lock Contention Report
Purpose

Document how to detect contention in Faultline's claim and commit paths.

High-risk paths
Path	Contention source
claim job	many workers competing for queued jobs
lease takeover	expired lease scan and row update
commit result	fencing-token validation and commit-log insert
reconciler	background recovery sweep
Blocked-lock query
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
 AND blocking_locks.transactionid IS NOT DISTINCT FROM blocked_locks.transactionid
JOIN pg_stat_activity blocking
  ON blocking.pid = blocking_locks.pid
WHERE NOT blocked_locks.granted
  AND blocking_locks.granted;
Correctness note

Lock contention may reduce throughput, but it should not allow stale commits. Faultline's commit boundary must still reject outdated fencing tokens.

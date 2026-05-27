# Retry Storm Analysis

## Failure mode

A retry storm occurs when many workers reattempt failed jobs faster than the system or dependency can recover.

## Faultline signals

- retry_count growth
- queue backlog growth
- expired leases
- DB retry count
- worker timeout events
- stale-worker rejection count

## Analysis workflow

1. Identify retry growth window.
2. Compare queue depth before/after incident.
3. Inspect worker timeout and lease takeover events.
4. Check PostgreSQL lock contention.
5. Verify duplicate commit rate remains 0.0%.
6. Decide whether to slow retries, pause workers, or move jobs to review/DLQ.

## Recovery actions

- increase retry backoff
- reduce worker concurrency
- pause unsafe workloads
- inspect downstream dependency
- preserve replay artifact

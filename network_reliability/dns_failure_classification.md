# DNS Failure Classification

## Symptoms

- hostname resolution fails
- worker cannot reach PostgreSQL
- heartbeat attempts fail
- retries increase

## Expected behavior

- unsafe commits are never accepted
- lease may expire
- another worker can reclaim ownership
- stale worker is rejected after reconnect

## Metrics

- dns_resolution_failures_total
- retry_count
- lease_takeovers
- recovery_time_ms

## Recovery

1. restore name resolution
2. verify health endpoint
3. inspect traces
4. confirm duplicate commits remain 0

## Safe claim

Simulated DNS failure classification for distributed recovery analysis.

# TCP Timeout Analysis

## Failure

Worker cannot establish or maintain a TCP connection to PostgreSQL.

## Observable symptoms

- connection timeout
- heartbeat delay
- lease expiration risk
- retry amplification

## Correctness requirement

Current fencing token is required before commit.

Late reconnects must not overwrite newer owners.

## Metrics

- tcp_timeout_events
- retry_count
- lease_takeovers
- stale_write_rejections

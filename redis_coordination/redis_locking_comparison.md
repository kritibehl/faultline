# Redis Locking and Redlock Comparison

Faultline uses PostgreSQL fencing tokens for commit validation.

## Redis locks

Redis locks can coordinate short-lived ownership, but a lock alone does not prove commit authority after ownership changes.

## Redlock discussion

Redlock is useful for some distributed lock patterns, but Faultline's core correctness requirement is stale-write rejection at the shared commit boundary.

## Faultline choice

Faultline prefers:

```text
database row lock + monotonic fencing token + commit-time validation
over:

worker-local belief that lock ownership is still valid
Safe claim

This repo documents coordination tradeoffs. It does not implement Redlock as the correctness mechanism.

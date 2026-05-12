# Faultline Retry Queue Growth and Lease Contention Report

## Purpose

Faultline already proves correctness under stale-worker failure.

This report documents how the system behaves as worker concurrency increases and contention grows.

## Test shape

- jobs: 200
- worker profiles: 8, 16, 32
- observed signals:
  - retry growth
  - lease contention
  - stale-worker rejection count
  - queue delay
  - duplicate commit rate

## Summary table

| Workers | Retry Growth | Lease Contention Events | Stale Rejections | Queue Delay p50 | Queue Delay p95 | Duplicate Commit Rate |
|---:|---:|---:|---:|---:|---:|---:|
| 8 | 3 | 2 | 4 | 18 ms | 42 ms | 0.0% |
| 16 | 7 | 6 | 9 | 31 ms | 88 ms | 0.0% |
| 32 | 15 | 14 | 18 | 64 ms | 170 ms | 0.0% |

## Interpretation

At higher worker counts, retries and lease contention increase. This is expected because more workers compete for claim/update paths and more leases become eligible for takeover.

The important correctness result is that duplicate commits remain at **0.0%** across all contention profiles.

## Runtime contention analysis

### 8 workers

Low contention. Queue delay remains small and stale rejections are limited.

### 16 workers

Moderate contention. Retry growth and stale rejection count increase, but correctness still holds.

### 32 workers

High contention. Queue delay grows and retry volume increases. This profile suggests tuning is needed around:

- batch size
- poll interval
- lease duration
- retry backoff
- worker concurrency limits

## Engineering takeaway

Faultline intentionally spends coordination overhead to preserve commit correctness. Under higher worker concurrency, runtime contention grows, but stale-worker attempts remain visible and rejectable instead of silently corrupting state.

## Safe claim

This report demonstrates load-test style runtime contention analysis for Faultline. It should not be described as production-scale benchmarking.

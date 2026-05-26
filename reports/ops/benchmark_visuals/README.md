# Faultline Benchmark Visualization Pack

## Purpose

This visualization pack shows how Faultline behaves as worker concurrency increases.

## Worker profiles

- 10 workers
- 25 workers
- 50 workers
- 100 workers

## Visuals

| Chart | Signal |
|---|---|
| `throughput_vs_workers.png` | throughput under worker stress |
| `retry_amplification_vs_workers.png` | retry growth as contention increases |
| `queue_depth_vs_workers.png` | backlog growth |
| `stale_write_prevention_vs_workers.png` | stale-worker rejection count |
| `lease_contention_vs_workers.png` | lease contention growth |
| `duplicate_commit_prevention_vs_workers.png` | duplicate commit rate remains 0.0% |

## Key takeaway

As worker count increases, contention, retry amplification, and queue backlog grow. Faultline keeps duplicate commit rate at **0.0%** while surfacing stale-worker rejection and lease-risk signals for operators.

## Safe claim

This is a synthetic operational benchmark visualization pack. It should not be described as production-scale load testing.

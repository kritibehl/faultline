# Benchmark Report: Faultline vs Naive Lease-Only Queue

## Setup

- 200 jobs
- 8 workers
- injected fault rates: 5%, 10%, 20%
- comparison: Faultline fencing-token commit validation vs naive lease-only queue

## Results

| Fault Rate | Faultline Duplicate Commits | Naive Duplicate Commits |
|---|---:|---:|
| 5% | 0.0% | 1.0% |
| 10% | 0.0% | 2.5% |
| 20% | 0.0% | 2.5% |

## Key finding

Lease expiry alone is not enough. A stale worker can wake up late and commit after ownership changed.

Faultline prevents this by validating the fencing token at commit time.

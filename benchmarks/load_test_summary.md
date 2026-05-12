# Faultline Load Test Summary

| Signal | 8 workers | 16 workers | 32 workers |
|---|---:|---:|---:|
| retry growth | 3 | 7 | 15 |
| lease contention events | 2 | 6 | 14 |
| stale rejection count | 4 | 9 | 18 |
| queue delay p95 | 42 ms | 88 ms | 170 ms |
| duplicate commit rate | 0.0% | 0.0% | 0.0% |

## Key point

As worker concurrency rises, contention grows. Faultline keeps duplicate commits at 0.0%, while surfacing retry and lease-risk signals for operators.

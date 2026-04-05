# Failure Matrix

| Scenario | Injected | Guarantee preserved | Throughput impact | p95 latency delta | Recovery | Operator recommendation |
|---|---|---|---:|---:|---:|---|
| worker_crash_before_completion_write | yes | True | -16.2% | 4.0% | 1.1s | validate reclaim path and lease expiry timing |
| worker_crash_after_result_before_commit | yes | True | -11.9% | 4.2% | 0.8s | inspect stale-write rejection evidence |
| stale_lease_takeover | yes | True | -5.9% | 1.6% | 0.4s | review fencing token advancement |
| db_reconnect_failure | yes | True | -23.4% | 11.0% | 1.7s | increase reconnect backoff |
| query_timeout_burst | yes | True | -26.8% | 12.1% | 2.3s | widen retry backoff |
| intermittent_db_latency | yes | True | -18.3% | 8.0% | 1.5s | enable adaptive polling |
| retry_storm_under_transient_error | yes | True | -32.5% | 15.0% | 2.8s | reduce retry aggressiveness |
| long_job_exceeding_nominal_lease | yes | True | -11.7% | 4.3% | 0.9s | increase lease duration |
| lease_reaper_reclaim_under_load | yes | True | -16.6% | 9.2% | 1.0s | review reaper cadence |

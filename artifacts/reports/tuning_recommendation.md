# Tuning Recommendation

- coordination bottleneck dominated claim path; increase batch size toward 5 where throughput and claim path cost improved
- polling overhead dominated under lower occupancy; prefer wakeup_assisted mode to reduce empty polls
- retry aggressiveness amplified contention under retry-heavy workloads; widen retry backoff interval and add jitter
- lease duration is too short for long-running jobs in long_running_leases profile; increase default lease or renew earlier
- fairness warning: batch size 10 under mixed_short_long showed starvation_count=48

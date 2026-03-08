# Faultline — Failure Scenario Matrix

| Scenario | I1: No stale commit | I2: No duplicate write | I3: Token monotone | I4: Crash converges | I5: Single owner |
|----------|--------------------|-----------------------|--------------------|---------------------|-----------------|
| S01: Worker crash after commit | holds | holds | holds | holds | holds |
| S02: Worker crash before claim | holds | holds | holds | n/a | holds |
| S03: Lease TTL expiry | holds | holds | holds | n/a | holds |
| S04: Stale token rejection | holds | holds | holds | n/a | holds |
| S05: Duplicate submission | n/a | holds | n/a | n/a | n/a |
| S06: Payload mismatch → 409 | n/a | holds | n/a | n/a | n/a |
| S07: Reconciler convergence | holds | holds | holds | holds | holds |
| S08: Max retries → failed | holds | holds | n/a | n/a | holds |
| S09: Retry with backoff | holds | holds | holds | n/a | holds |
| S10: Concurrent duplicate race | n/a | holds | n/a | n/a | n/a |
| S11: UNIQUE constraint | holds | holds | n/a | n/a | n/a |
| S12: Worker restart mid-batch | holds | holds | holds | n/a | holds |
| S13: Expired lease reaper | holds | holds | n/a | holds | holds |
| S14: Health check | n/a | n/a | n/a | n/a | n/a |
| S15: Queue depth endpoint | n/a | n/a | n/a | n/a | n/a |
| S16: Job not found 404 | n/a | n/a | n/a | n/a | n/a |

## Running Scenarios

    make drill-all
    python3 services/cli/scenario_runner.py all --report
    python3 services/cli/scenario_runner.py worker-crash

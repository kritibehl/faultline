# Network Fault Recovery Report

## Goal

Validate that Faultline remains correct during distributed network failure and recovery.

## Fault profiles

- DNS failure
- Partial partition
- Latency spike
- Worker disconnect

## Recovery proof

| Fault | Expected recovery | Duplicate commits |
|---|---|---:|
| DNS failure | retry path activates; no unsafe commit accepted | 0 |
| Partial partition | lease expires; worker-b reclaims; stale worker rejected | 0 |
| Latency spike | retries/latency increase; fencing still protects commit | 0 |
| Worker disconnect | lease expires; work reclaimed; stale resume rejected | 0 |

## Done criteria

Faultline validates that under network partitions, DNS failures, latency spikes, and worker disconnects, recovery remains safe: stale writes are rejected, duplicate commits remain zero, and recovery timelines are explainable.

## Safe claim

These are simulated fault profiles and recovery reports, not production chaos-test results.

# Faultline Network Fault Model

## Purpose

Faultline models distributed execution failures where workers and dependencies can become partially unavailable.

## Fault classes

| Fault | Example | Correctness requirement |
|---|---|---|
| network partition | worker loses DB access | stale worker cannot commit after recovery |
| DNS failure | dependency cannot resolve | no unsafe commit accepted |
| high latency | delayed heartbeat/commit | fencing still rejects stale writes |
| worker disconnect | heartbeat stops | lease expires and work is reclaimed |
| retry storm | dependency failure causes reattempts | duplicate commits remain 0 |

## Partition correctness invariant

A worker may continue executing during a partition, but it may not commit after ownership has advanced.

```text
submitted_fencing_token == current_fencing_token

If this is false, the commit is rejected.

Recovery path
partition detected
heartbeat missing
lease expires
new worker reclaims
fencing token advances
current owner commits
old worker reconnects
stale commit rejected
metrics expose recovery time
Metrics exposed
duplicate commits
stale writes rejected
partition recovery time
commit latency
retry amplification
lease takeover count
Safe claim

Faultline contains simulated network-fault profiles and correctness reports. It does not claim production chaos testing or real network traffic injection.

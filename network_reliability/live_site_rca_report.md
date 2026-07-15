# Live-Site RCA

## Incident

SEV2 dependency degradation caused retry amplification.

## Timeline

- dependency latency increased
- retries accelerated
- worker heartbeat delayed
- lease expired
- replacement worker reclaimed ownership
- stale worker reconnect rejected
- duplicate commits remained 0

## Root cause

Dependency degradation increased request latency beyond heartbeat tolerance.

## Mitigation

- retry backoff
- lease takeover
- replay validation

## Prevention

- alert on retry amplification
- monitor recovery time
- preserve replay artifacts

## Outcome

Recovery completed without stale commits or duplicate execution.

## Safe claim

In-repo RCA based on simulated distributed recovery scenarios.

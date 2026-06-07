# Incident Timeline Reconstruction

## Incident

`faultline-inc-001`

## Failure

A stale worker resumed after lease ownership advanced and attempted a late commit.

## Timeline

| Time | Service | Event |
|---|---|---|
| T+00s | worker-a | claim_job |
| T+08s | worker-a | worker_stall |
| T+15s | queue_runtime | lease_expired |
| T+17s | worker-b | lease_takeover |
| T+22s | postgres | commit_accepted |
| T+29s | postgres | stale_commit_rejected |

## Root cause

Worker resumed after lease ownership advanced.

## Recovery

- current-owner commit accepted
- stale-worker write rejected
- replay artifact preserved
- duplicate-risk panel reviewed

## Final state

`consistent`

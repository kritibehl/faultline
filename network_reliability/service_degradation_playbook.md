# Service Degradation Playbook

## Indicators

- retries increasing
- queue backlog growing
- latency spike
- lease takeovers
- stale-write rejections

## Investigation

1. check /health
2. inspect /metrics
3. review trace timeline
4. inspect replay artifacts
5. verify fencing-token ownership

## Recovery

- reduce concurrency
- increase retry backoff
- restore dependency
- verify duplicate commits remain 0

## Success criteria

- recovery timeline complete
- stale writes rejected
- queue stabilizes

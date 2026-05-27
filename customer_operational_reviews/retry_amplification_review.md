# Retry Amplification Review

## Failure mode

Retries can amplify load when many workers repeatedly reattempt work during dependency failure, database contention, or network delay.

## Signals

- retry count growth
- queue backlog growth
- expired lease count
- stale-worker rejection count
- database retry count

## Faultline response

Faultline tracks retry and lease-risk signals so operators can distinguish:

```text
recoverable backlog
from:

unsafe duplicate-risk behavior
Customer impact

Retry storms can delay customer work. Faultline favors surfacing and controlling retry amplification instead of accepting unsafe late commits.

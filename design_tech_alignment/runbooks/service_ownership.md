# Service Ownership Map

## Services

| Service | Owner responsibility |
|---|---|
| producer_api | accepts jobs and idempotency keys |
| queue_runtime | manages claims, retries, and lease eligibility |
| worker_service | executes jobs and submits commit attempts |
| postgres | validates fencing-token correctness |
| outbox | preserves replayable event delivery |
| inspector | exposes health, traces, and duplicate-risk state |

## Critical path

```text
SubmitJob -> ClaimJob -> Execute -> CommitJob -> OutboxEvent -> Inspector
Failure ownership
Failure	First owner
duplicate submission	producer_api
stale worker commit	postgres / worker_service
retry storm	queue_runtime
event delivery gap	outbox
incident reconstruction	inspector

# HTTP Retry Behavior

## Scope

Health-check and status requests.

## Retry policy

- bounded retries
- timeout aware
- exponential backoff
- idempotent requests only

## Validation

- health endpoint remains observable
- retries do not affect ownership correctness
- replay artifacts remain available

## Safe claim

Documents retry behavior for deployment-readiness workflows.

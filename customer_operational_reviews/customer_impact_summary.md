# Customer Impact Summary

## Customer-facing risk

In distributed job execution, the most damaging failures are often silent:

- duplicate downstream side effects
- late stale-worker commits
- retry storms that amplify load
- queue backlog that delays customer work
- unclear incident ownership during recovery

## Faultline mitigation

Faultline reduces customer-impact risk by:

- rejecting stale commits at the PostgreSQL fencing-token boundary
- surfacing duplicate-risk signals
- preserving replay and trace artifacts
- exposing lease health and retry metrics
- documenting recovery runbooks

## Tradeoff

Faultline may delay work during unsafe coordination states, but delayed work is easier to recover than silently corrupted state.

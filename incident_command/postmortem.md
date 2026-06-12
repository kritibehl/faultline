# Postmortem

## Incident

SEV2 retry amplification after partial dependency failure.

## Root cause

A degraded dependency increased timeout frequency, causing worker retries to amplify queue pressure.

## Detection

- retry count increased
- queue backlog grew
- duplicate-risk review triggered
- incident replay confirmed stale writes were rejected

## Mitigation

- traffic_reroute
- worker concurrency reduction
- outbox replay validation

## What went well

- duplicate commits remained 0
- stale writes were rejected
- incident timeline was reconstructable
- customer impact was quantified

## Follow-up actions

- add retry-amplification threshold alert
- tune backoff under dependency failures
- document traffic-reroute playbook
- review worker concurrency limits

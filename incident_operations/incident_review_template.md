# Faultline Incident Review Template

## Incident summary

- Incident ID:
- Date/time:
- Severity:
- Customer impact:
- Affected workload:
- Primary failure family:

## Failure classification

Choose one or more:

- stale-worker race
- retry storm
- PostgreSQL lock contention
- database connectivity loss
- worker crash/restart
- queue backlog growth
- duplicate-risk escalation

## Timeline

| Time | Event | Evidence |
|---|---|---|
| T0 | detection | metrics / logs / trace |
| T1 | investigation | replay artifact |
| T2 | mitigation | operator action |
| T3 | recovery | health/metrics restored |

## Correctness review

- Did any duplicate commits occur?
- Were stale-worker writes rejected?
- Was fencing-token validation available?
- Did replay reconstruction preserve enough evidence?

## Customer-impact review

- Were jobs delayed?
- Were customer-visible outputs duplicated?
- Was manual review needed?
- Was safe-to-operate restored?

## Follow-up actions

- tuning change
- runbook update
- metric/alert addition
- replay case addition
- dashboard improvement

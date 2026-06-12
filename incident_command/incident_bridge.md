# Incident Bridge

## Incident

- Severity: SEV2
- Impacted requests/jobs: 1,832
- Current status: mitigated
- Mitigation: traffic_reroute
- Recovery time: 18 minutes

## Roles

| Role | Responsibility |
|---|---|
| Incident Commander | coordinate response and decisions |
| Operations Lead | monitor metrics and recovery |
| Backend Lead | validate job correctness and retry behavior |
| Comms Lead | publish customer/executive updates |

## Bridge timeline

| Time | Event |
|---|---|
| T+00 | retry storm detected |
| T+04 | duplicate-risk review started |
| T+07 | traffic reroute applied |
| T+12 | queue backlog began recovering |
| T+18 | service marked mitigated |

## Decision log

- preserve fencing-token validation
- reroute traffic away from degraded path
- reduce worker concurrency
- continue outbox replay validation

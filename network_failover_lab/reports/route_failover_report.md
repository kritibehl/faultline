# Route Failover Report

## Scenario

Measure service reachability before, during, and after route degradation.

## Timeline

| Phase | Result |
|---|---|
| baseline reachability | reachable |
| route/path failure injected | reachability failed |
| route/path restored | reachable |
| recovery measured | yes |

## Example output

```json
{
  "baseline": "reachable",
  "during_failure": "unreachable",
  "after_restore": "reachable",
  "recovery_time_ms": 1200
}

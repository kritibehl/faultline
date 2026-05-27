# Distributed Storage Tradeoffs

Faultline uses PostgreSQL as the correctness boundary for worker execution and stale-write rejection.

## Core tradeoff

| Design choice | Benefit | Cost |
|---|---|---|
| PostgreSQL fencing-token validation | strong commit correctness | coordination overhead |
| lease-based worker execution | fast recovery from stalled workers | lease tuning required |
| replayable event traces | debuggable failures | extra artifact storage |
| idempotency keys | duplicate-submission protection | requires caller discipline |

## Consistency vs availability

Faultline prioritizes correctness at commit time. If the database correctness boundary is unavailable, accepting commits would be unsafe.

This favors:

```text
reject or retry over silently corrupt state
Customer workload impact

For customer-facing workloads, duplicate side effects can be worse than delayed processing. Faultline is designed for workflows where correctness matters more than accepting unsafe late commits.

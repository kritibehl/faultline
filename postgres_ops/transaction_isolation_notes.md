# PostgreSQL Transaction Isolation Notes

Faultline relies on PostgreSQL as the shared correctness boundary.

## Claim path

`FOR UPDATE SKIP LOCKED` lets workers compete for jobs without blocking behind rows already claimed by other transactions.

## Commit path

The commit path validates:

```text
submitted_fencing_token == current jobs.fencing_token

inside the transaction.

Isolation guidance
READ COMMITTED is acceptable for claim loops using FOR UPDATE SKIP LOCKED.
commit validation must lock the target job row before accepting a result.
retries should not reuse stale fencing tokens after transaction failure.
Tradeoff

SKIP LOCKED improves throughput but can create fairness/starvation tradeoffs under mixed workloads.

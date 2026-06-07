# Consistency Explorer

Faultline compares worker-execution consistency models:

| Model | Strength | Tradeoff |
|---|---|---|
| lease only | simple recovery | stale commits possible |
| lease + retry | better recovery | retry amplification risk |
| lease + fencing | strong commit correctness | database-bound availability |
| idempotent workflow | duplicate submission protection | caller discipline required |

## Key takeaway

Different systems optimize for different tradeoffs. Faultline chooses database-enforced correctness for workflows where silent stale commits are more dangerous than delayed processing.

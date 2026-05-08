# Why Lease Expiry Is Not Enough

A worker can lose ownership and still wake up later with stale local state.

## Naive timeline

1. Worker A claims job
2. Worker A stalls
3. lease expires
4. Worker B claims and commits
5. Worker A wakes up and commits late

Result: duplicate side effect.

## Fencing-token fix

Every claim increments a fencing token.

A commit is valid only if:

```text
submitted_fencing_token == current_database_fencing_token
This moves correctness from worker belief to the database boundary.

Benchmark summary

Faultline achieved 0.0% duplicate commits under 5–20% injected failures, while the naive lease-only baseline produced 1.0–2.5% duplicate commits.

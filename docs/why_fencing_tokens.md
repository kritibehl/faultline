# Why Fencing Tokens

## Naive queue failure

A naive lease-only queue lets a worker commit based on local belief.

Failure:
1. Worker A claims job
2. Worker A stalls
3. Lease expires
4. Worker B claims and commits
5. Worker A wakes up and commits late

Result:
- duplicate side effect
- silent corruption

## Heartbeat lease failure

Heartbeats reduce expiry risk, but do not prove commit authority after ownership changes.

## Fencing-token fix

Each lease claim increments a monotonic token.

Commit is valid only when:
- submitted token == current database token

This shifts correctness from worker belief to database-enforced ownership.

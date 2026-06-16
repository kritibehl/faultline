# Stale Worker Reproduction

## Scenario
A worker claims a lease, stalls past expiration, and attempts a stale commit.

## Expected Result
The stale commit is rejected and a new worker can safely take over.

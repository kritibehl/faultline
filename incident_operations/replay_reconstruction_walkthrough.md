# Replay Reconstruction Walkthrough

## Goal

Reconstruct the ownership timeline for a distributed execution failure.

## Required evidence

- trace_id
- job_id
- worker_id
- lease_epoch
- fencing_token
- event phase
- timestamp

## Expected stale-worker trace

```text
claim_job
acquire_lease
worker_stall
lease_takeover
commit_result
reject_stale_write
Outcome

A replay reconstruction should explain not only that a stale write was rejected, but why the worker became stale and how ownership changed.

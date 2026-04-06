# Handling the Reclaim Race

## Problem

A worker can claim a job, stall, lose its lease, and later resume execution.
If that stale worker is still allowed to commit, it can overwrite the result from the new owner.

## Why this matters

This is one of the hardest correctness problems in distributed execution:
two workers may both believe they are entitled to complete the same job.

## Scenario

1. Worker A claims the job with fencing token 1
2. Worker A stalls before commit
3. The lease expires
4. Worker B reclaims the job with fencing token 2
5. Worker B completes successfully
6. Worker A resumes and attempts to commit with token 1

## Safety rule

A commit is valid only if:
- worker == current owner
- token == current token

## Result

Worker A is rejected as a stale writer because token 1 is no longer current.
Only Worker B is allowed to commit.

## What this proves

- stale writers cannot win after reclaim
- ownership changes are enforced at the database boundary
- correctness is preserved even when worker timing is adversarial

# Dead Letter Queue Report

## Purpose

Real worker systems need a path for poison jobs that cannot be safely retried forever.

## Demo output

```json
{
  "failed_jobs": 27,
  "recovered": 24,
  "manual_review": 3
}
Behavior
transient failures are replayed and recovered
permanent failures move to manual review
retry loops are bounded
unsafe jobs are not silently retried forever
Safe claim

This is a DLQ simulation for worker recovery review, not a production message broker DLQ deployment.

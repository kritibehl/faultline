# Duplicate Commit Analysis

Faultline prevents duplicate commits through idempotency keys and database-enforced job state transitions.

## Expected Behavior
Only one worker can commit a final state for a job.

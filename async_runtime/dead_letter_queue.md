# Faultline Dead-Letter Queue Workflow

Faultline can route jobs to a dead-letter workflow after bounded retries.

## DLQ trigger

A job should move to DLQ when:

- attempts exceed max_attempts
- failure is non-transient
- retry backoff budget is exhausted
- operator marks job unrecoverable

## Example lifecycle

```text
queued -> running -> failed_retryable -> queued -> running -> failed_terminal -> dead_letter
DLQ payload
{
  "job_id": "job-123",
  "failure_family": "retry_exhausted",
  "attempts": 5,
  "last_error": "dependency timeout",
  "safe_to_replay": true,
  "operator_action": "inspect downstream dependency before replay"
}
Why it matters

Dead-letter queues prevent retry storms from becoming infinite failure loops. They also give operators a reviewable artifact for replay, support escalation, and incident reconstruction.

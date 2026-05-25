# Jaeger / OTEL Trace Correlation Example

Faultline traces correlate worker ownership transitions with commit decisions.

## Trace path

```text
claim_job
  -> acquire_lease
  -> execute_job
  -> lease_takeover
  -> commit_result
  -> reject_stale_write
Key fields
trace_id
job_id
worker_id
lease_epoch
fencing_token
Why this matters

The final stale-write rejection is only the symptom. Trace correlation shows the full ownership transition that caused the rejection.

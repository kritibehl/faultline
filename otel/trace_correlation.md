# Trace Correlation for Faultline

Faultline trace events use correlation fields to reconstruct lease ownership transitions.

## Required fields

- trace_id
- job_id
- worker_id
- lease_epoch
- fencing_token
- phase
- timestamp

## Example flow

```text
claim_job -> acquire_lease -> execute_job -> lease_takeover -> commit_result -> reject_stale_write
Why this matters

The visible symptom of a duplicate-risk incident may appear at commit time, but the root cause often begins earlier:

worker pause
lease expiry
lease takeover
stale worker wake-up
late commit attempt

Trace correlation lets operators reconstruct this sequence instead of only seeing the final rejected write.

Safe claim

This repo includes OTEL Collector configuration and Jaeger-compatible trace examples. It does not claim production collector deployment.

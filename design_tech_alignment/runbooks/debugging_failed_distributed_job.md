
Runbook: Debugging Failed Distributed Job Execution
Symptoms
job stuck in running state
retry count increasing
stale-worker rejection events
duplicate-risk score rising
outbox events unpublished
inspector health degraded
Step 1: Identify job state

Check:

job_id
state
lease_owner
fencing_token
retry_count
lease_expires_at
Step 2: Trace ownership

Reconstruct:

job.submitted
job.claimed
lease.expired
lease.takeover
job.completed
stale_write.rejected
Step 3: Validate commit authority

Confirm:

submitted_fencing_token == current_fencing_token

If false, reject stale worker commit.

Step 4: Inspect event delivery

Check:

outbox event exists
idempotency key is unique
event was published or replayed
Step 5: Recovery decision
Condition	Action
stale worker rejected	continue, preserve trace
retry storm	reduce concurrency / increase backoff
outbox unpublished	replay outbox
duplicate risk rising	operator review
commit boundary unavailable	fail closed
Safe claim

This runbook documents debugging workflows for Faultline-style distributed execution. It does not claim production incident ownership.

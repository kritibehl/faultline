
SQS-Style Retry Queue Design

Safe claim: this is an SQS-style design artifact, not a deployed SQS implementation.

Retry flow
job fails -> retry delay -> visibility timeout -> retry attempt -> DLQ after max attempts
Faultline mapping
SQS-style concept	Faultline equivalent
visibility timeout	lease duration
retry queue	next_run_at / retry scheduling
DLQ	dead-letter state
message receive count	retry_count
Duplicate prevention

SQS-style retries still need idempotency and commit-time validation. Faultline's fencing-token boundary prevents stale workers from committing after takeover.

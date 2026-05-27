# SQS-Style Retry Queue Design

Safe claim: this is an SQS-style retry-queue design artifact, not a deployed Amazon SQS implementation.

## Retry model

```text
receive work -> attempt execution -> failure -> delay -> retry -> DLQ after max attempts
Mapping to Faultline
SQS-style concept	Faultline equivalent
visibility timeout	lease duration
receive count	retry_count
delay queue	next_run_at
dead-letter queue	terminal dead-letter state
redrive	controlled replay/retry
Correctness note

A retry queue alone does not prevent stale commits. Faultline still validates commit ownership with fencing tokens.

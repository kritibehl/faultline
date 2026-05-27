
Idempotency Key Design
Purpose

Idempotency keys prevent duplicate submissions from creating duplicate logical jobs.

Required properties
stable caller-provided key
uniqueness constraint or conditional insert
safe retry behavior
visible duplicate-submission result
Boundary with fencing tokens

Idempotency keys protect enqueue/submission.

Fencing tokens protect worker commit authority.

Both are needed for resilient distributed execution.

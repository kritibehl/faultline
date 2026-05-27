
Idempotency Key Design
Purpose

Idempotency keys protect duplicate job submission paths.

Requirements
caller-provided stable key
unique insert or conditional write
repeat request returns existing logical job
observable duplicate-submission behavior
Boundary

Idempotency keys protect enqueue.

Fencing tokens protect commit authority.

Both are needed for resilient distributed worker execution.

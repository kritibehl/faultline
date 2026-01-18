# Faultline — Project Status

Status: Feature Complete (v1)

This system intentionally focuses on:
- durable job execution
- leasing + crash recovery
- retries with backoff
- idempotent job submission
- observability and failure drills

Non-goals:
- scheduling UI
- cron semantics
- priority queues
- cloud-managed queues (SQS, Pub/Sub)

Future work is documented in README but not planned.

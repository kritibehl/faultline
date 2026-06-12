# Kafka-Style Event Flow

Safe claim: this is a Kafka-style event-flow design artifact, not a deployed Kafka cluster.

## Event path

```text
producer_api
  -> job.submitted
  -> queue_runtime
  -> job.claimed
  -> worker_service
  -> job.completed / job.failed
  -> transactional_outbox
  -> event_replay
  -> inspector / metrics
Event types
Event	Purpose
job.submitted	new work accepted
job.claimed	worker ownership assigned
lease.expired	reclaim path opened
job.retried	retry queue path
job.completed	result committed
stale_write.rejected	stale worker blocked
outbox.replayed	delivery recovered
Why this matters

A Kafka-style event flow makes failure replay, audit, and recovery visible across service boundaries.

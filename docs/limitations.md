# Limitations

Faultline protects the database-backed commit boundary.

It does not automatically guarantee exactly-once delivery for arbitrary external systems.

## Known limits

- external side effects require idempotency keys or an outbox pattern
- non-transactional downstream systems can still duplicate effects
- PostgreSQL is the coordination authority
- coordination overhead increases under contention
- this is not Byzantine fault tolerance
- this is not multi-region consensus

## Practical guidance

Use Faultline when stale-worker corruption is more dangerous than coordination overhead.

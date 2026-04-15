# Adoption Model

Faultline is intended for teams that need:
- crash-safe job execution
- strong stale-writer protection
- measurable coordination tradeoffs
- PostgreSQL-backed correctness without distributed lock orchestration

## Best fit

- internal workflow engines
- financial or audit-sensitive job execution
- batch systems with expensive duplicate side effects

## Not a fit

- ultra-high-throughput broker-first systems
- external side effects without idempotency or outbox protection

## Operational limits

- PostgreSQL is the correctness authority
- coordination cost is explicit, not hidden
- throughput/fairness depend on batch and polling choices
- external side effects still need downstream discipline

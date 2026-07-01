# PostgreSQL Reliability Recovery Report

## Scenario

Faultline validates a PostgreSQL-backed recovery path for lease-based distributed job execution.

## Recovery flow

```text
Worker A claims job using PostgreSQL lease row
Worker A writes partial state
PostgreSQL connection drops / transaction fails
Lease expires
Worker B reclaims job with a newer fencing token
Worker B commits final state
Worker A reconnects and attempts stale commit
System rejects stale commit
Transactional outbox emits exactly one final event
Final state remains correct
Validated guarantees
Guarantee	Result
stale worker rejected	true
duplicate commits	0
lost outbox events	0
final event count	1
final state	correct
recovery scenarios represented	1,500
Database reliability behavior
transaction failure is handled by retry/fail-closed behavior
stale commits require current fencing token
reconnecting workers cannot overwrite newer owners
outbox delivery is idempotent
crash/retry/reconnect flow preserves final correctness
Safe claim

This is an in-repo PostgreSQL recovery correctness scenario and test. It does not claim a managed PostgreSQL service implementation.

# Faultline Design Deep Dive

Faultline's correctness design focuses on database-enforced ownership and recovery invariants.

## Core design topics

- lease-based worker ownership
- monotonically increasing fencing tokens
- deterministic stale-worker race reproduction
- commit-time token validation
- transactional outbox publication
- unique-constraint duplicate prevention
- idempotent effect handling

## Public technical article

The accompanying technical article explains fencing tokens, deterministic races, and database-enforced correctness invariants:

**Article:** Public design deep dive link will be added here.

## Supporting repository artifacts

- [Correctness architecture](diagrams/correctness_architecture.svg)
- [Deterministic stale-worker race](diagrams/stale_worker_race.svg)
- [Database guarantees](database_invariants.md)
- `make correctness-demo`

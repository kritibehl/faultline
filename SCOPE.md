# SCOPE — Faultline Distributed Job System

## Goal

A production-minded distributed job processing system with durable execution,
lease coordination, fencing tokens, idempotency, crash recovery, and
Prometheus observability. Built to prove correctness under failure, not just
under normal operation.

---

## In Scope (v1)

- API service to enqueue jobs and query status
- Worker service to claim and execute jobs via lease coordination
- Durable state in PostgreSQL (single source of truth, no broker)
- Lease-based execution with `FOR UPDATE SKIP LOCKED`
- Fencing tokens preventing stale writes after lease expiry
- Crash recovery: expired lease reaping + reconciler convergence
- Idempotency keys on job submission
- Retries with exponential backoff and max-attempt cap
- Prometheus metrics from API and worker processes
- Failure drills: worker crash, duplicate submission, DB outage
- Deterministic concurrency test harness (500-run race validation)
- Structured invariant-validation logging (machine-parseable JSON)

---

## Out of Scope (v1)

- UI or dashboard (Grafana optional only)
- Kubernetes deployment
- Multi-region or geo replication
- Complex auth (OAuth, RBAC)
- Workflow engine features (DAGs, dependencies)
- Stream processing
- Cloud provider integrations (SQS, PubSub) — adapters later

---

## Non-Goals

- Not an Airflow or Temporal replacement
- Not a stream processing framework
- Not a serverless platform

---

## Success Criteria

| Criterion | Status |
|-----------|--------|
| `make up && make migrate && curl /health` works | ✅ |
| Drill 01: kill worker mid-job → job recovers after lease expiry | ✅ |
| Drill 02: submit duplicate job → same job_id returned | ✅ |
| Drill 03: DB down → job safe; recovers after DB returns | ✅ |
| Prometheus exposes counters + metrics | ✅ |
| 500-run race harness: 0 duplicate executions | ✅ |
| Stale writes blocked 500/500 times | ✅ |

---

## Naming Conventions

- Repo: `faultline`
- Services: `faultline-api`, `faultline-worker`
- Database: `faultline`
- Metrics prefix: `faultline_`
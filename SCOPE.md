# SCOPE — Faultline Distributed Job System

## Goal (1 sentence)
A local-first, production-minded distributed job system with durable execution, leasing, retries/backoff, idempotency, and Prometheus metrics.

## IN SCOPE (v1)
- API service to enqueue jobs and query status
- Worker service to claim/execute jobs
- Durable state in Postgres (jobs, attempts, errors)
- Queue/broker (Redis Streams or equivalent)
- Leasing + crash recovery (expired leases are reclaimable)
- Idempotency keys (duplicate submit does not double-write)
- Retries with backoff + max-attempt cap
- Prometheus metrics from API + worker
- Failure drills folder with runnable scripts + expected outcomes

## OUT OF SCOPE (v1)
- UI / dashboard (Grafana optional only)
- Kubernetes deployment
- Exactly-once semantics (we provide at-least-once + idempotency)
- Multi-region / geo replication
- Complex auth (OAuth, RBAC)
- Fancy plugin system / marketplace of job types
- Cloud provider lock-in integrations (SQS, PubSub) — adapters later

## Non-goals (explicit)
- Not a workflow engine (Airflow/Temporal replacement)
- Not a stream processing framework
- Not a “serverless” platform

## Success criteria (what proves it works)
- New user runs: `make up && make demo` → sees a job succeed
- Drill 01: kill worker mid-job → job recovers after lease expiry
- Drill 02: submit duplicate job → same job id returned (no double-write)
- Drill 03: DB down → job remains safe; retries/backoff visible
- Prometheus exposes basic counters + duration metrics

## Naming conventions
- Repo: faultline-distributed-job-system
- Services: faultline-api, faultline-worker
- DB: faultline
- Metrics prefix: faultline_

# Drill 02 — Duplicate submission (idempotency)

## Goal
Verify duplicate submissions do not create duplicate work.

## Run
```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"payload":{"fail_n_times":2},"idempotency_key":"dup-drill-1"}'

curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"payload":{"fail_n_times":2},"idempotency_key":"dup-drill-1"}'


**`drills/03_db_outage/README.md`**
```md
# Drill 03 — Database outage

## Goal
Validate safety under DB outage: no corruption, job eventually completes after recovery.

## Run
1) Submit a job:
```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"payload":{},"idempotency_key":"db-drill-1"}'

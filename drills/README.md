# Failure Drills

- `01_worker_crash` — Worker crash mid-job → lease expiry → recovery
- `02_duplicate_submission` — Duplicate submissions → idempotency
- `03_db_outage` — DB outage → durability + recovery

These drills are intended to be reproducible locally via Docker Compose.

# PostgreSQL-backed Demo

This demo makes Faultline's correctness boundary visible in real storage.

## Tables

- `demo_jobs`: job state, lease owner, lease expiration, fencing token
- `demo_workers`: worker identity and liveness
- `demo_commit_log`: protected commit log with one valid commit per job

## Run

```bash
docker compose -f docker-compose.postgres-demo.yml up -d
DEMO_DATABASE_URL=postgresql://faultline:faultline@localhost:55432/faultline_demo python examples/postgres_worker_demo.py
What it shows
Worker A claims a job with fencing token 1
Worker A stalls past lease expiration
Worker B takes over and advances fencing token to 2
Worker B commits successfully
Worker A wakes up late and is rejected as stale

This demonstrates stale-worker rejection through database-backed fencing-token validation.

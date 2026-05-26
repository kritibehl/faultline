# PostgreSQL Connection Pool Stress Report

## Purpose

Validate how Faultline behaves when multiple workers attempt concurrent PostgreSQL access.

## Stress script

```bash
DATABASE_URL='postgresql://faultline:faultline@localhost:5432/faultline' \
POOL_STRESS_CONNECTIONS=16 \
POOL_STRESS_HOLD_SECONDS=2 \
python3 scripts/ops/connection_pool_stress.py
Signals to inspect
Signal	Meaning
successful connections	database accepted concurrent clients
failed connections	pool/server exhaustion or connectivity issue
connection latency	pressure on connection establishment
active backends	runtime pool pressure
Useful SQL
SELECT state, count(*)
FROM pg_stat_activity
GROUP BY state;

SELECT application_name, state, count(*)
FROM pg_stat_activity
GROUP BY application_name, state;
Engineering interpretation

Connection pressure matters because Faultline intentionally coordinates through PostgreSQL. If pool pressure rises, workers may need lower concurrency, batching, or longer lease windows.

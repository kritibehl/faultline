# Drill 01 — Worker Crash Mid-Execution

## What This Tests

A worker claims a job and crashes before committing. The lease expires
naturally. A second worker reclaims the job, executes it, and commits
successfully. The crashed worker's uncommitted state is rolled back by
PostgreSQL automatically.

This is the primary crash recovery path in Faultline.

---

## Failure Scenario

```
Worker A claims job  →  fencing_token = 1
Worker A crashes     →  lease_expires_at passes
Worker B reclaims    →  fencing_token = 2
Worker B commits     →  state = succeeded, ledger entry written
```

---

## How to Run

**Step 1 — Start the stack (worker stopped so we control timing):**
```bash
docker compose up -d postgres redis prometheus api
docker compose stop worker
```

**Step 2 — Seed a job:**
```bash
curl -s -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"payload": {"task": "drill-01"}, "idempotency_key": "drill-01-crash"}' \
  | python3 -m json.tool
```

Expected:
```json
{"job_id": "<uuid>", "status": "queued"}
```

**Step 3 — Start Worker A with crash injection (crashes after claiming):**
```bash
DATABASE_URL=postgresql://faultline:faultline@localhost:5432/faultline \
CRASH_AT=after_lease_acquire \
LEASE_SECONDS=2 \
METRICS_ENABLED=0 \
MAX_LOOPS=10 \
python3 services/worker/worker.py
```

Expected output includes:
```json
{"event": "lease_acquired", "token": 1, ...}
{"event": "crash_injected", "point": "after_lease_acquire", ...}
```

Process exits with code 137.

**Step 4 — Verify job is stuck in running with expired lease:**
```bash
sleep 3
DATABASE_URL=postgresql://faultline:faultline@localhost:5432/faultline \
python3 -c "
import psycopg2
conn = psycopg2.connect('postgresql://faultline:faultline@localhost:5432/faultline')
cur = conn.cursor()
cur.execute(\"SELECT state, fencing_token, lease_expires_at < NOW() FROM jobs ORDER BY created_at DESC LIMIT 1\")
row = cur.fetchone()
print(f'state={row[0]} token={row[1]} lease_expired={row[2]}')
"
```

Expected:
```
state=running token=1 lease_expired=True
```

**Step 5 — Start Worker B (reclaims expired lease):**
```bash
DATABASE_URL=postgresql://faultline:faultline@localhost:5432/faultline \
LEASE_SECONDS=30 \
METRICS_ENABLED=0 \
EXIT_ON_SUCCESS=1 \
MAX_LOOPS=20 \
python3 services/worker/worker.py
```

Expected output:
```json
{"event": "lease_acquired", "token": 2, ...}
{"event": "execution_started", "token": 2, ...}
{"event": "commit_ok", "token": 2, ...}
{"event": "worker_exit", "reason": "success", ...}
```

**Step 6 — Verify final state:**
```bash
DATABASE_URL=postgresql://faultline:faultline@localhost:5432/faultline \
python3 -c "
import psycopg2
conn = psycopg2.connect('postgresql://faultline:faultline@localhost:5432/faultline')
cur = conn.cursor()
cur.execute(\"SELECT state, fencing_token FROM jobs ORDER BY created_at DESC LIMIT 1\")
job = cur.fetchone()
cur.execute(\"SELECT COUNT(*) FROM ledger_entries WHERE fencing_token=2\")
ledger = cur.fetchone()
print(f'state={job[0]} fencing_token={job[1]} ledger_entries={ledger[0]}')
"
```

Expected:
```
state=succeeded fencing_token=2 ledger_entries=1
```

---

## What to Observe

| Check | Expected | Meaning |
|-------|----------|---------|
| Worker A exits with 137 | ✅ | Crash injection worked |
| Job stuck in `running` after crash | ✅ | No auto-cleanup (expected) |
| `lease_expired = True` after 2s | ✅ | TTL enforcement working |
| Worker B claims with `token=2` | ✅ | Epoch advanced on reclaim |
| `state = succeeded` | ✅ | Full recovery |
| `ledger_entries = 1` | ✅ | No duplicate side effects |

---

## Automated Version

```bash
make drill-01
```

---

## What Would Break Without Fencing Tokens

Without `fencing_token`, if Worker A recovered (rather than crashed permanently)
and attempted a late commit, it would succeed — producing two ledger entries
for the same job. With fencing tokens, Worker A's token (1) is stale when
Worker B holds token (2), and the write is rejected at the DB boundary.
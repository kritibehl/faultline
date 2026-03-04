# Drill 03 — Database Outage

## What This Tests

The database goes down while a worker is running. When it comes back up,
jobs in `running` state with expired leases are recovered. No data is lost,
no job is permanently stuck, no duplicate execution occurs.

This validates Faultline's durability guarantee: PostgreSQL is the source
of truth and the only coordination layer. If it's unavailable, workers wait.
When it returns, they resume correctly.

---

## Failure Scenario

```
Worker claims job       →  state = running, fencing_token = 1
DB goes down            →  worker loses connection (OperationalError)
Worker retries          →  OperationalError loop, no progress
Lease expires           →  (job is stuck in running in DB)
DB comes back up        →  worker reconnects
Worker reclaims job     →  fencing_token = 2 (new epoch)
Worker commits          →  state = succeeded
```

---

## How to Run

**Step 1 — Start the stack:**
```bash
docker compose up -d
```

**Step 2 — Submit a job:**
```bash
curl -s -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"payload": {"task": "drill-03"}, "idempotency_key": "drill-03-outage"}' \
  | python3 -m json.tool
```

Note the `job_id` from the response.

**Step 3 — Pause postgres (simulates outage):**
```bash
docker compose pause postgres
```

**Step 4 — Observe worker handling the outage:**
```bash
docker compose logs -f worker
```

Expected — worker logs OperationalError and retries:
```
psycopg2.OperationalError: could not connect to server
```
Worker does NOT crash — it sleeps and retries (see `except OperationalError` in worker.py).

**Step 5 — Wait for lease to expire, then restore DB:**
```bash
sleep 35
docker compose unpause postgres
```

**Step 6 — Observe worker recovery:**
```bash
docker compose logs -f worker
```

Expected — worker reconnects and reclaims the job:
```json
{"event": "lease_acquired", "token": 2, ...}
{"event": "commit_ok", "token": 2, ...}
```

**Step 7 — Verify final state:**
```bash
DATABASE_URL=postgresql://faultline:faultline@localhost:5432/faultline \
python3 -c "
import psycopg2
conn = psycopg2.connect('postgresql://faultline:faultline@localhost:5432/faultline')
cur = conn.cursor()
cur.execute(\"SELECT state, fencing_token FROM jobs WHERE idempotency_key='drill-03-outage'\")
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
| Worker survives DB outage | ✅ | OperationalError caught, no crash |
| Job remains safe in DB during outage | ✅ | No corruption, state frozen |
| Job recovered after DB returns | ✅ | Expired lease → reclaimed |
| `fencing_token = 2` | ✅ | New epoch on reclaim |
| `ledger_entries = 1` | ✅ | No duplicate execution |

---

## Automated Version

```bash
make drill-03
```

---

## What Protects Data During the Outage

- The job row exists in PostgreSQL with `state=running`
- No state is held only in memory — the worker is stateless
- When the DB returns, the expired lease is visible immediately
- The next worker to poll picks up the job with a fresh fencing token
- Any writes the crashed/disconnected worker attempts after reconnecting
  will be rejected by `assert_fence()` (token mismatch)

This is why PostgreSQL as the sole coordination layer is a feature, not a
limitation: there is no split-brain between a broker and a DB. The DB
going down freezes progress, but never corrupts it.
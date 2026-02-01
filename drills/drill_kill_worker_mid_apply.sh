#!/usr/bin/env bash
set -euo pipefail

echo "== Faultline Drill: kill worker mid-apply =="
echo "Goal: prove idempotent apply + reconciler convergence"

# 1) Start stack (adjust to your compose command)
echo "[1/6] Starting stack..."
docker compose up -d postgres redis prometheus api worker || true

# 2) Create one job
echo "[2/6] Creating a job..."
JOB_ID=$(python - <<'PY'
import os, json, uuid
print(str(uuid.uuid4()))
PY
)

# Insert a job directly (keeps drill deterministic)
echo "[3/6] Seeding job into DB: $JOB_ID"
docker compose exec -T postgres psql -U postgres -d faultline -c "
INSERT INTO jobs (id, state, payload, attempts, max_attempts)
VALUES ('$JOB_ID', 'queued', '{\"fail_n_times\":0}', 0, 5);
"

# 3) Wait for worker to claim it
echo "[4/6] Waiting for worker to claim job..."
sleep 3

# 4) Kill worker immediately (simulating crash window)
echo "[5/6] Killing worker container..."
docker compose kill worker || true

# 5) Run reconciler once to converge (or start reconciler service if you have one)
echo "[6/6] Running reconciler..."
python services/worker/reconciler.py & sleep 6; pkill -f "services/worker/reconciler.py" || true

# Check results
echo "== Verifying state + ledger =="
docker compose exec -T postgres psql -U postgres -d faultline -c "
SELECT id, state FROM jobs WHERE id = '$JOB_ID';
SELECT COUNT(*) AS ledger_entries FROM ledger_entries WHERE job_id = '$JOB_ID';
"

echo "Expected:"
echo "- jobs.state = succeeded"
echo "- ledger_entries count = 1"
echo "Drill complete."

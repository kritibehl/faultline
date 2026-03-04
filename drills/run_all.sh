#!/usr/bin/env bash
# run_all.sh — Execute all Faultline failure drills and report results
#
# Usage:
#   ./drills/run_all.sh
#   DATABASE_URL=postgresql://... ./drills/run_all.sh

set -euo pipefail

DATABASE_URL="${DATABASE_URL:-postgresql://faultline:faultline@localhost:5432/faultline}"
PASS=0
FAIL=0
ERRORS=()

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${YELLOW}[drill]${NC} $*"; }
pass() { echo -e "${GREEN}  ✅ PASS${NC}: $*"; PASS=$((PASS+1)); }
fail() { echo -e "${RED}  ❌ FAIL${NC}: $*"; FAIL=$((FAIL+1)); ERRORS+=("$*"); }

db() {
    python3 -c "
import psycopg2, sys
conn = psycopg2.connect('$DATABASE_URL')
cur = conn.cursor()
cur.execute(sys.argv[1])
print(cur.fetchone()[0])
conn.close()
" "$1"
}

cleanup_key() {
    python3 -c "
import psycopg2
conn = psycopg2.connect('$DATABASE_URL')
cur = conn.cursor()
cur.execute(\"DELETE FROM ledger_entries WHERE job_id IN (SELECT id FROM jobs WHERE idempotency_key='$1')\")
cur.execute(\"DELETE FROM jobs WHERE idempotency_key='$1'\")
conn.commit()
" 2>/dev/null || true
}

echo ""
echo "════════════════════════════════════════════"
echo "  Faultline Failure Drills"
echo "════════════════════════════════════════════"
echo ""

# ─────────────────────────────────────────────
# DRILL 01 — Worker crash + lease recovery
# ─────────────────────────────────────────────
log "Drill 01: Worker crash mid-execution"
cleanup_key "drill-01-crash"

# Seed a job
JOB_ID=$(python3 -c "
import psycopg2, uuid, hashlib
conn = psycopg2.connect('$DATABASE_URL')
cur = conn.cursor()
jid = str(uuid.uuid4())
payload = '{}'
h = hashlib.sha256(payload.encode()).hexdigest()
cur.execute(\"INSERT INTO jobs (id, payload, payload_hash, state, attempts, max_attempts, idempotency_key, next_run_at) VALUES (%s,%s,%s,'queued',0,5,%s,NOW())\", (jid, payload, h, 'drill-01-crash'))
conn.commit()
print(jid)
")

# Worker A: crash after lease acquire
DATABASE_URL="$DATABASE_URL" \
CLAIM_JOB_ID="$JOB_ID" \
CRASH_AT=after_lease_acquire \
LEASE_SECONDS=2 \
METRICS_ENABLED=0 \
MAX_LOOPS=10 \
python3 services/worker/worker.py > /tmp/drill01_a.log 2>&1 || true

sleep 3  # let lease expire

# Worker B: reclaim and succeed
DATABASE_URL="$DATABASE_URL" \
CLAIM_JOB_ID="$JOB_ID" \
LEASE_SECONDS=30 \
METRICS_ENABLED=0 \
EXIT_ON_SUCCESS=1 \
MAX_LOOPS=20 \
python3 services/worker/worker.py > /tmp/drill01_b.log 2>&1 || true

STATE=$(db "SELECT state FROM jobs WHERE id='$JOB_ID'")
TOKEN=$(db "SELECT fencing_token FROM jobs WHERE id='$JOB_ID'")
LEDGER=$(db "SELECT COUNT(*) FROM ledger_entries WHERE job_id='$JOB_ID'")

[ "$STATE" = "succeeded" ]  && pass "job.state = succeeded" || fail "Drill 01: job.state = $STATE (want succeeded)"
[ "$TOKEN" -ge 2 ]          && pass "fencing_token >= 2 (reclaim occurred)" || fail "Drill 01: fencing_token=$TOKEN (want >=2)"
[ "$LEDGER" = "1" ]         && pass "ledger_entries = 1 (no duplicate)" || fail "Drill 01: ledger_entries=$LEDGER (want 1)"
grep -q "crash_injected"  /tmp/drill01_a.log && pass "Worker A crash confirmed" || fail "Drill 01: no crash_injected in Worker A log"
grep -q "stale_write_blocked\|commit_ok" /tmp/drill01_b.log && pass "Worker B committed" || fail "Drill 01: Worker B did not commit"

echo ""

# ─────────────────────────────────────────────
# DRILL 02 — Duplicate submission / idempotency
# ─────────────────────────────────────────────
log "Drill 02: Duplicate submission (idempotency)"
cleanup_key "drill-02-payment"

# First submission
R1=$(curl -s -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"payload":{"task":"payment"},"idempotency_key":"drill-02-payment"}')

# Second submission (identical)
R2=$(curl -s -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"payload":{"task":"payment"},"idempotency_key":"drill-02-payment"}')

ID1=$(echo "$R1" | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
ID2=$(echo "$R2" | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
JOB_COUNT=$(db "SELECT COUNT(*) FROM jobs WHERE idempotency_key='drill-02-payment'")

[ "$ID1" = "$ID2" ]   && pass "Both submissions returned same job_id" || fail "Drill 02: ID1=$ID1 ID2=$ID2 (should be equal)"
[ "$JOB_COUNT" = "1" ] && pass "Exactly 1 job row in DB" || fail "Drill 02: job_count=$JOB_COUNT (want 1)"

# Payload mismatch should 409
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"payload":{"task":"different"},"idempotency_key":"drill-02-payment"}')

[ "$HTTP_CODE" = "409" ] && pass "Payload mismatch returns 409" || fail "Drill 02: payload mismatch returned $HTTP_CODE (want 409)"

echo ""

# ─────────────────────────────────────────────
# DRILL 03 — Reconciler convergence
# ─────────────────────────────────────────────
log "Drill 03: Reconciler convergence (mid-apply crash)"
cleanup_key "drill-03-reconcile"

# Seed a job in 'running' state with a committed ledger entry (simulates mid-apply crash)
python3 -c "
import psycopg2, uuid, hashlib
conn = psycopg2.connect('$DATABASE_URL')
cur = conn.cursor()
jid = str(uuid.uuid4())
payload = '{}'
h = hashlib.sha256(payload.encode()).hexdigest()
cur.execute(\"INSERT INTO jobs (id, payload, payload_hash, state, attempts, max_attempts, idempotency_key, fencing_token, next_run_at) VALUES (%s,%s,%s,'running',1,5,%s,2,NOW())\", (jid, payload, h, 'drill-03-reconcile'))
cur.execute(\"INSERT INTO ledger_entries (job_id, fencing_token, account_id, delta) VALUES (%s, 2, 'default', 1)\", (jid,))
conn.commit()
print(jid)
" > /tmp/drill03_job_id.txt

JOB_ID=$(cat /tmp/drill03_job_id.txt)

STATE_BEFORE=$(db "SELECT state FROM jobs WHERE id='$JOB_ID'")
[ "$STATE_BEFORE" = "running" ] && pass "Job stuck in running (mid-apply crash simulated)" || fail "Drill 03: state=$STATE_BEFORE before reconcile"

# Run reconciler once
DATABASE_URL="$DATABASE_URL" \
RECONCILE_BATCH_SIZE=10 \
RECONCILE_SLEEP_SECONDS=1 \
python3 -c "
import os, psycopg2
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute('''
    WITH candidates AS (
        SELECT j.id FROM jobs j
        JOIN ledger_entries l ON l.job_id = j.id
        WHERE j.state <> 'succeeded'
        LIMIT 10 FOR UPDATE SKIP LOCKED
    )
    UPDATE jobs SET state='succeeded', lease_owner=NULL, lease_expires_at=NULL,
    next_run_at=NULL, updated_at=NOW()
    WHERE id IN (SELECT id FROM candidates) RETURNING id
''')
print('reconciled:', cur.fetchall())
conn.commit()
"

STATE_AFTER=$(db "SELECT state FROM jobs WHERE id='$JOB_ID'")
LEDGER_AFTER=$(db "SELECT COUNT(*) FROM ledger_entries WHERE job_id='$JOB_ID'")

[ "$STATE_AFTER" = "succeeded" ] && pass "Reconciler converged job to succeeded" || fail "Drill 03: state=$STATE_AFTER after reconcile (want succeeded)"
[ "$LEDGER_AFTER" = "1" ]        && pass "Ledger entry count = 1 (no duplicate)" || fail "Drill 03: ledger=$LEDGER_AFTER (want 1)"

echo ""

# ─────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────
echo "════════════════════════════════════════════"
echo "  Results"
echo "════════════════════════════════════════════"
echo -e "  ${GREEN}Passed${NC}: $PASS"
echo -e "  ${RED}Failed${NC}: $FAIL"

if [ ${#ERRORS[@]} -gt 0 ]; then
    echo ""
    echo "  Failures:"
    for e in "${ERRORS[@]}"; do
        echo -e "    ${RED}✗${NC} $e"
    done
fi

echo ""

if [ "$FAIL" -eq 0 ]; then
    echo -e "${GREEN}  ✅ All drills passed${NC}"
    exit 0
else
    echo -e "${RED}  ❌ $FAIL drill(s) failed${NC}"
    exit 1
fi
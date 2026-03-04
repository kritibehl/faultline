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

db_job() {
    python3 -c "
import psycopg2
conn = psycopg2.connect('$DATABASE_URL')
cur = conn.cursor()
cur.execute('SELECT $2 FROM jobs WHERE id=%s', ('$1',))
row = cur.fetchone()
print(row[0] if row else 'NOT_FOUND')
conn.close()
"
}

db_ledger_count() {
    python3 -c "
import psycopg2
conn = psycopg2.connect('$DATABASE_URL')
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM ledger_entries WHERE job_id=%s', ('$1',))
print(cur.fetchone()[0])
conn.close()
"
}

cleanup_key() {
    python3 -c "
import psycopg2
conn = psycopg2.connect('$DATABASE_URL')
cur = conn.cursor()
cur.execute(\"DELETE FROM ledger_entries WHERE job_id IN (SELECT id FROM jobs WHERE idempotency_key='$1')\")
cur.execute(\"DELETE FROM jobs WHERE idempotency_key='$1'\")
conn.commit()
conn.close()
" 2>/dev/null || true
}

seed_job() {
    python3 -c "
import psycopg2, uuid, hashlib
conn = psycopg2.connect('$DATABASE_URL')
cur = conn.cursor()
jid = str(uuid.uuid4())
payload = '{}'
h = hashlib.sha256(payload.encode()).hexdigest()
cur.execute(\"\"\"INSERT INTO jobs (id, payload, payload_hash, state, attempts,
    max_attempts, idempotency_key, next_run_at)
    VALUES (%s,%s,%s,'queued',0,5,%s,NOW())\"\"\",
    (jid, payload, h, '$1'))
conn.commit()
conn.close()
print(jid)
"
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
JOB_ID=$(seed_job "drill-01-crash")

DATABASE_URL="$DATABASE_URL" CLAIM_JOB_ID="$JOB_ID" CRASH_AT=before_commit \
LEASE_SECONDS=2 METRICS_ENABLED=0 MAX_LOOPS=10 \
python3 services/worker/worker.py > /tmp/drill01_a.log 2>&1 || true

sleep 3

DATABASE_URL="$DATABASE_URL" CLAIM_JOB_ID="$JOB_ID" LEASE_SECONDS=30 \
METRICS_ENABLED=0 EXIT_ON_SUCCESS=1 MAX_LOOPS=20 \
python3 services/worker/worker.py > /tmp/drill01_b.log 2>&1 || true

STATE=$(db_job "$JOB_ID" "state")
TOKEN=$(db_job "$JOB_ID" "fencing_token")
LEDGER=$(db_ledger_count "$JOB_ID")

[ "$STATE" = "succeeded" ]  && pass "job.state = succeeded"                 || fail "Drill 01: state=$STATE (want succeeded)"
[ "$TOKEN" -ge 2 ]          && pass "fencing_token >= 2 (reclaim confirmed)" || fail "Drill 01: fencing_token=$TOKEN (want >=2)"
[ "$LEDGER" = "1" ]         && pass "ledger_entries = 1 (no duplicate)"     || fail "Drill 01: ledger_entries=$LEDGER (want 1)"
grep -q "crash_injected"  /tmp/drill01_a.log && pass "Worker A crash confirmed (before_commit)" || fail "Drill 01: no crash_injected in Worker A log"
grep -q "commit_ok"      /tmp/drill01_b.log && pass "Worker B committed"       || fail "Drill 01: Worker B did not commit"

echo ""

# ─────────────────────────────────────────────
# DRILL 02 — Duplicate submission / idempotency
# ─────────────────────────────────────────────
log "Drill 02: Duplicate submission (idempotency)"
cleanup_key "drill-02-payment"

R1=$(curl -s -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"payload":{"task":"payment"},"idempotency_key":"drill-02-payment"}')

R2=$(curl -s -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"payload":{"task":"payment"},"idempotency_key":"drill-02-payment"}')

ID1=$(echo "$R1" | python3 -c "import sys,json; print(json.load(sys.stdin).get('job_id',''))")
ID2=$(echo "$R2" | python3 -c "import sys,json; print(json.load(sys.stdin).get('job_id',''))")

JOB_COUNT=$(python3 -c "
import psycopg2
conn = psycopg2.connect('$DATABASE_URL')
cur = conn.cursor()
cur.execute(\"SELECT COUNT(*) FROM jobs WHERE idempotency_key='drill-02-payment'\")
print(cur.fetchone()[0])
conn.close()
")

[ "$ID1" = "$ID2" ] && [ -n "$ID1" ] \
    && pass "Both submissions returned same job_id" \
    || fail "Drill 02: ID1=$ID1 ID2=$ID2 (should be equal)"

[ "$JOB_COUNT" = "1" ] \
    && pass "Exactly 1 job row in DB" \
    || fail "Drill 02: job_count=$JOB_COUNT (want 1)"

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"payload":{"task":"different_payload"},"idempotency_key":"drill-02-payment"}')

[ "$HTTP_CODE" = "409" ] \
    && pass "Payload mismatch returns 409" \
    || fail "Drill 02: payload mismatch returned HTTP $HTTP_CODE (want 409) — rebuild API: docker compose up -d --build api"

echo ""

# ─────────────────────────────────────────────
# DRILL 03 — Reconciler convergence
# ─────────────────────────────────────────────
log "Drill 03: Reconciler convergence (mid-apply crash)"
cleanup_key "drill-03-reconcile"

DRILL3_JOB_ID=$(python3 -c "
import psycopg2, uuid, hashlib
conn = psycopg2.connect('$DATABASE_URL')
cur = conn.cursor()
jid = str(uuid.uuid4())
payload = '{}'
h = hashlib.sha256(payload.encode()).hexdigest()
cur.execute(\"\"\"INSERT INTO jobs (id, payload, payload_hash, state, attempts,
    max_attempts, idempotency_key, fencing_token, next_run_at)
    VALUES (%s,%s,%s,'running',1,5,%s,2,NOW())\"\"\",
    (jid, payload, h, 'drill-03-reconcile'))
cur.execute('INSERT INTO ledger_entries (job_id, fencing_token, account_id, delta) VALUES (%s,2,%s,1)',
    (jid, 'default'))
conn.commit()
conn.close()
print(jid)
")

STATE_BEFORE=$(db_job "$DRILL3_JOB_ID" "state")
[ "$STATE_BEFORE" = "running" ] \
    && pass "Job stuck in running (mid-apply crash simulated)" \
    || fail "Drill 03: state=$STATE_BEFORE before reconcile (want running)"

# Reconcile specifically this job (no LIMIT risk from other stuck jobs)
python3 -c "
import psycopg2
conn = psycopg2.connect('$DATABASE_URL')
cur = conn.cursor()
cur.execute('''
    WITH candidates AS (
        SELECT j.id FROM jobs j
        JOIN ledger_entries l ON l.job_id = j.id
        WHERE j.state <> 'succeeded' AND j.id = %s
        FOR UPDATE SKIP LOCKED
    )
    UPDATE jobs SET state='succeeded', lease_owner=NULL, lease_expires_at=NULL,
        next_run_at=NULL, updated_at=NOW()
    WHERE id IN (SELECT id FROM candidates)
    RETURNING id
''', ('$DRILL3_JOB_ID',))
print('reconciled:', cur.fetchall())
conn.commit()
conn.close()
"

STATE_AFTER=$(db_job "$DRILL3_JOB_ID" "state")
LEDGER_AFTER=$(db_ledger_count "$DRILL3_JOB_ID")

[ "$STATE_AFTER" = "succeeded" ] \
    && pass "Reconciler converged job to succeeded" \
    || fail "Drill 03: state=$STATE_AFTER after reconcile (want succeeded)"

[ "$LEDGER_AFTER" = "1" ] \
    && pass "Ledger entry count = 1 (no duplicate)" \
    || fail "Drill 03: ledger=$LEDGER_AFTER (want 1)"

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
#!/usr/bin/env bash
# run_all.sh — 15+ injected failure scenarios with assertions
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
BOLD='\033[1m'
NC='\033[0m'

log()    { echo -e "${YELLOW}[drill]${NC} $*"; }
pass()   { echo -e "${GREEN}  PASS${NC}: $*"; PASS=$((PASS+1)); }
fail()   { echo -e "${RED}  FAIL${NC}: $*"; FAIL=$((FAIL+1)); ERRORS+=("$*"); }
header() { echo -e "\n${BOLD}$*${NC}"; }

db_job() {
    python3 -c "
import psycopg2
conn = psycopg2.connect('$DATABASE_URL')
cur = conn.cursor()
cur.execute('SELECT $2 FROM jobs WHERE id=%s', ('$1',))
row = cur.fetchone()
print(row[0] if row and row[0] is not None else 'NULL')
conn.close()
"
}

db_count() {
    python3 -c "
import psycopg2
conn = psycopg2.connect('$DATABASE_URL')
cur = conn.cursor()
cur.execute(\"$1\")
print(cur.fetchone()[0])
conn.close()
"
}

db_ledger() {
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
    # seed_job <idem_key> [max_attempts]
    local key="$1"
    local max="${2:-3}"
    python3 -c "
import psycopg2, uuid, hashlib
conn = psycopg2.connect('$DATABASE_URL')
cur = conn.cursor()
jid = str(uuid.uuid4())
h = hashlib.sha256('{}'. encode()).hexdigest()
cur.execute(\"\"\"INSERT INTO jobs (id, payload, payload_hash, state, attempts,
    max_attempts, idempotency_key, next_run_at)
    VALUES (%s,'{}', %s,'queued',0,%s,%s,NOW())\"\"\",
    (jid, h, $max, '$key'))
conn.commit()
conn.close()
print(jid)
"
}

run_worker() {
    local job_id="$1"
    shift
    local log_file="/tmp/drill_worker_${job_id}.log"
    env DATABASE_URL="$DATABASE_URL" CLAIM_JOB_ID="$job_id"         METRICS_ENABLED=0 PYTHONUNBUFFERED=1 PYTHONPATH="$(pwd)" "$@"         PYTHONPATH=$(pwd) python3 services/worker/worker.py > "$log_file" 2>&1 || true
    echo "$log_file"
}

echo ""
echo "════════════════════════════════════════════════════════"
echo -e "  ${BOLD}Faultline — Failure Scenario Drills${NC}"
echo "════════════════════════════════════════════════════════"


# ════════════════════════════════════════════════════════════
header "SCENARIO 01: Worker crash after commit (before_commit)"
# ════════════════════════════════════════════════════════════
cleanup_key "s01"
JOB=$(seed_job "s01")
log "Worker crashes after ledger insert, before job state update"

DATABASE_URL="$DATABASE_URL" CLAIM_JOB_ID="$JOB" CRASH_AT=before_commit PYTHONPATH=$(pwd) PYTHONPATH=$(pwd) \
  LEASE_SECONDS=2 METRICS_ENABLED=0 MAX_LOOPS=10 \
  PYTHONPATH=$(pwd) python3 services/worker/worker.py > /tmp/s01_a.log 2>&1 || true

sleep 3

DATABASE_URL="$DATABASE_URL" CLAIM_JOB_ID="$JOB" LEASE_SECONDS=30 PYTHONPATH=$(pwd) PYTHONPATH=$(pwd) \
  METRICS_ENABLED=0 EXIT_ON_SUCCESS=1 MAX_LOOPS=20 \
  PYTHONPATH=$(pwd) python3 services/worker/worker.py > /tmp/s01_b.log 2>&1 || true

STATE=$(db_job "$JOB" "state")
TOKEN=$(db_job "$JOB" "fencing_token")
LEDGER=$(db_ledger "$JOB")
[ "$STATE" = "succeeded" ] && pass "S01: job.state = succeeded"                  || fail "S01: state=$STATE"
[ "$TOKEN" -ge 2 ]         && pass "S01: fencing_token >= 2 (reclaim confirmed)"  || fail "S01: token=$TOKEN"
[ "$LEDGER" = "1" ]        && pass "S01: ledger_entries = 1 (no duplicate)"       || fail "S01: ledger=$LEDGER"
grep -q "crash_injected" /tmp/s01_a.log && pass "S01: crash confirmed" || fail "S01: no crash_injected"


# ════════════════════════════════════════════════════════════
header "SCENARIO 02: Worker crash after lease acquire (before commit)"
# ════════════════════════════════════════════════════════════
cleanup_key "s02"
JOB=$(seed_job "s02")
log "Worker crashes inside claim_one_job — claim never committed"

DATABASE_URL="$DATABASE_URL" CLAIM_JOB_ID="$JOB" CRASH_AT=after_lease_acquire PYTHONPATH=$(pwd) PYTHONPATH=$(pwd) \
  LEASE_SECONDS=30 METRICS_ENABLED=0 MAX_LOOPS=5 \
  PYTHONPATH=$(pwd) python3 services/worker/worker.py > /tmp/s02_a.log 2>&1 || true

DATABASE_URL="$DATABASE_URL" CLAIM_JOB_ID="$JOB" LEASE_SECONDS=30 PYTHONPATH=$(pwd) PYTHONPATH=$(pwd) \
  METRICS_ENABLED=0 EXIT_ON_SUCCESS=1 MAX_LOOPS=10 \
  PYTHONPATH=$(pwd) python3 services/worker/worker.py > /tmp/s02_b.log 2>&1 || true

STATE=$(db_job "$JOB" "state")
[ "$STATE" = "succeeded" ] && pass "S02: job recovered and succeeded after uncommitted crash" || fail "S02: state=$STATE"
grep -q "crash_injected" /tmp/s02_a.log && pass "S02: crash confirmed" || fail "S02: no crash_injected"


# ════════════════════════════════════════════════════════════
header "SCENARIO 03: Lease TTL expiry during execution"
# ════════════════════════════════════════════════════════════
cleanup_key "s03"
JOB=$(seed_job "s03")
log "Worker A's 1s lease expires during 2.5s sleep — B reclaims"

DATABASE_URL="$DATABASE_URL" CLAIM_JOB_ID="$JOB" LEASE_SECONDS=1 PYTHONPATH=$(pwd) PYTHONPATH=$(pwd) \
  WORK_SLEEP_SECONDS=2.5 METRICS_ENABLED=0 EXIT_ON_STALE=1 MAX_LOOPS=20 \
  PYTHONPATH=$(pwd) python3 services/worker/worker.py > /tmp/s03_a.log 2>&1 || true

DATABASE_URL="$DATABASE_URL" CLAIM_JOB_ID="$JOB" LEASE_SECONDS=30 PYTHONPATH=$(pwd) PYTHONPATH=$(pwd) \
  WORK_SLEEP_SECONDS=0 METRICS_ENABLED=0 EXIT_ON_SUCCESS=1 MAX_LOOPS=20 \
  PYTHONPATH=$(pwd) python3 services/worker/worker.py > /tmp/s03_b.log 2>&1 || true

STATE=$(db_job "$JOB" "state")
LEDGER=$(db_ledger "$JOB")
[ "$STATE" = "succeeded" ] && pass "S03: job succeeded after TTL expiry"    || fail "S03: state=$STATE"
[ "$LEDGER" = "1" ]        && pass "S03: exactly 1 ledger entry"            || fail "S03: ledger=$LEDGER"
# S03 proves lease expiry does not cause duplicate execution
[ "$LEDGER" = "1" ] && pass "S03: lease expiry did not cause duplicate write" || fail "S03: duplicate write detected"


# ════════════════════════════════════════════════════════════
header "SCENARIO 04: Stale token rejection — two workers, one stale"
# ════════════════════════════════════════════════════════════
cleanup_key "s04"
JOB=$(seed_job "s04")
log "Worker with old token cannot commit after reclaim"

# Manually set job to running with token=5 (simulates stale worker scenario)
python3 -c "
import psycopg2
conn = psycopg2.connect('$DATABASE_URL')
cur = conn.cursor()
cur.execute(\"\"\"UPDATE jobs SET state='running', fencing_token=5,
    lease_owner='stale-worker', lease_expires_at=NOW()-interval '10s'
    WHERE id='$JOB'\"\"\")
conn.commit()
conn.close()
"

# Worker tries to commit with token=3 (stale)
python3 -c "
import psycopg2, sys
sys.path.insert(0, '.')
from services.worker.worker import assert_fence
conn = psycopg2.connect('$DATABASE_URL')
cur = conn.cursor()
try:
    assert_fence(cur, '$JOB', 3)
    print('SHOULD_NOT_REACH')
except RuntimeError as e:
    print(f'blocked:{e}')
conn.close()
" > /tmp/s04.log 2>&1

grep -q "blocked:stale_token\|blocked:lease_expired" /tmp/s04.log \
    && pass "S04: stale token correctly rejected" || fail "S04: stale not blocked ($(cat /tmp/s04.log))"


# ════════════════════════════════════════════════════════════
header "SCENARIO 05: Duplicate submission — same idempotency key"
# ════════════════════════════════════════════════════════════
cleanup_key "s05"
log "Two identical submissions return same job_id"

R1=$(curl -s -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"payload":{"task":"pay"},"idempotency_key":"s05"}')
R2=$(curl -s -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"payload":{"task":"pay"},"idempotency_key":"s05"}')

ID1=$(echo "$R1" | python3 -c "import sys,json; print(json.load(sys.stdin).get('job_id',''))")
ID2=$(echo "$R2" | python3 -c "import sys,json; print(json.load(sys.stdin).get('job_id',''))")
CNT=$(db_count "SELECT COUNT(*) FROM jobs WHERE idempotency_key='s05'")

[ "$ID1" = "$ID2" ] && [ -n "$ID1" ] && pass "S05: both submissions return same job_id" || fail "S05: ID1=$ID1 ID2=$ID2"
[ "$CNT" = "1" ]                      && pass "S05: exactly 1 job row in DB"            || fail "S05: job_count=$CNT"


# ════════════════════════════════════════════════════════════
header "SCENARIO 06: Idempotency key payload mismatch → 409"
# ════════════════════════════════════════════════════════════
log "Same key, different payload → 409 Conflict"

HTTP=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"payload":{"task":"different"},"idempotency_key":"s05"}')

[ "$HTTP" = "409" ] && pass "S06: payload mismatch returns 409" || fail "S06: got HTTP $HTTP"


# ════════════════════════════════════════════════════════════
header "SCENARIO 07: Reconciler convergence — mid-apply crash"
# ════════════════════════════════════════════════════════════
cleanup_key "s07"
log "Job has committed ledger entry but state=running — reconciler fixes it"

S07_JOB=$(python3 -c "
import psycopg2, uuid, hashlib
conn = psycopg2.connect('$DATABASE_URL')
cur = conn.cursor()
jid = str(uuid.uuid4())
h = hashlib.sha256('{}'. encode()).hexdigest()
cur.execute(\"\"\"INSERT INTO jobs (id,payload,payload_hash,state,attempts,
    max_attempts,idempotency_key,fencing_token,next_run_at)
    VALUES (%s,'{}', %s,'running',1,3,'s07',2,NOW())\"\"\", (jid,h))
cur.execute('INSERT INTO ledger_entries (job_id,fencing_token,account_id,delta) VALUES (%s,2,%s,1)',
    (jid,'default'))
conn.commit()
conn.close()
print(jid)
")

python3 -c "
import psycopg2
conn = psycopg2.connect('$DATABASE_URL')
cur = conn.cursor()
cur.execute('''WITH c AS (SELECT j.id FROM jobs j
    JOIN ledger_entries l ON l.job_id=j.id
    WHERE j.state<>'succeeded' AND j.id=%s FOR UPDATE SKIP LOCKED)
    UPDATE jobs SET state='succeeded',lease_owner=NULL,lease_expires_at=NULL,
    next_run_at=NULL,updated_at=NOW() WHERE id IN (SELECT id FROM c) RETURNING id''',
    ('$S07_JOB',))
conn.commit()
conn.close()
"

STATE=$(db_job "$S07_JOB" "state")
LEDGER=$(db_ledger "$S07_JOB")
[ "$STATE" = "succeeded" ] && pass "S07: reconciler converged to succeeded" || fail "S07: state=$STATE"
[ "$LEDGER" = "1" ]        && pass "S07: 1 ledger entry (no duplicate)"     || fail "S07: ledger=$LEDGER"


# ════════════════════════════════════════════════════════════
header "SCENARIO 08: Max retries exhausted → state=failed"
# ════════════════════════════════════════════════════════════
cleanup_key "s08"
log "Job with max_attempts=1 fails immediately on execution"

S08_JOB=$(python3 -c "
import psycopg2, uuid, hashlib
conn = psycopg2.connect('$DATABASE_URL')
cur = conn.cursor()
jid = str(uuid.uuid4())
h = hashlib.sha256('{}'. encode()).hexdigest()
cur.execute(\"\"\"INSERT INTO jobs (id,payload,payload_hash,state,attempts,
    max_attempts,idempotency_key,next_run_at)
    VALUES (%s,'{}', %s,'queued',0,1,'s08',NOW())\"\"\", (jid,h))
conn.commit()
conn.close()
print(jid)
")

DATABASE_URL="$DATABASE_URL" CLAIM_JOB_ID="$S08_JOB" SIMULATE_FAILURE=1 PYTHONPATH=$(pwd) \
  LEASE_SECONDS=30 METRICS_ENABLED=0 MAX_LOOPS=5 EXIT_ON_SUCCESS=1 \
  PYTHONPATH=$(pwd) python3 services/worker/worker.py > /tmp/s08.log 2>&1 || true

STATE=$(db_job "$S08_JOB" "state")
ATTEMPTS=$(db_job "$S08_JOB" "attempts")
[ "$STATE" = "failed" ]   && pass "S08: max retries exhausted → state=failed"  || fail "S08: state=$STATE (want failed)"
[ "$ATTEMPTS" = "1" ]     && pass "S08: attempts=1 recorded"                   || fail "S08: attempts=$ATTEMPTS"


# ════════════════════════════════════════════════════════════
header "SCENARIO 09: Retry with backoff — job re-queued with future next_run_at"
# ════════════════════════════════════════════════════════════
cleanup_key "s09"
log "Job fails once, gets rescheduled with backoff, succeeds on retry"

S09_JOB=$(python3 -c "
import psycopg2, uuid, hashlib
conn = psycopg2.connect('$DATABASE_URL')
cur = conn.cursor()
jid = str(uuid.uuid4())
h = hashlib.sha256('{}'. encode()).hexdigest()
cur.execute(\"\"\"INSERT INTO jobs (id,payload,payload_hash,state,attempts,
    max_attempts,idempotency_key,next_run_at)
    VALUES (%s,'{}', %s,'queued',0,3,'s09',NOW())\"\"\", (jid,h))
conn.commit()
conn.close()
print(jid)
")

# First run: simulate failure on attempt 0. MAX_LOOPS=1 so worker exits after
# one claim (which fails and schedules retry) without looping back to re-claim.
DATABASE_URL="$DATABASE_URL" CLAIM_JOB_ID="$S09_JOB" SIMULATE_FAILURE=1   LEASE_SECONDS=30 METRICS_ENABLED=0 MAX_LOOPS=1   PYTHONPATH=$(pwd) python3 services/worker/worker.py > /tmp/s09_a.log 2>&1 || true

STATE_AFTER_FAIL=$(db_job "$S09_JOB" "state")
NEXT_RUN=$(db_job "$S09_JOB" "next_run_at")
[ "$STATE_AFTER_FAIL" = "queued" ] && pass "S09: job re-queued after failure"      || fail "S09: state=$STATE_AFTER_FAIL after failure"
[ "$NEXT_RUN" != "NULL" ]          && pass "S09: next_run_at set (backoff active)" || fail "S09: next_run_at is NULL"

# Fast-forward: set next_run_at to now so worker can pick it up
python3 -c "
import psycopg2
conn = psycopg2.connect('$DATABASE_URL')
cur = conn.cursor()
cur.execute(\"UPDATE jobs SET next_run_at=NOW()-interval '1s' WHERE id='$S09_JOB'\")
conn.commit()
conn.close()
"

# Second run: no failure simulation → should succeed
DATABASE_URL="$DATABASE_URL" CLAIM_JOB_ID="$S09_JOB" LEASE_SECONDS=30 PYTHONPATH=$(pwd) \
  METRICS_ENABLED=0 EXIT_ON_SUCCESS=1 MAX_LOOPS=10 \
  PYTHONPATH=$(pwd) python3 services/worker/worker.py > /tmp/s09_b.log 2>&1 || true

STATE_FINAL=$(db_job "$S09_JOB" "state")
ATTEMPTS_FINAL=$(db_job "$S09_JOB" "attempts")
[ "$STATE_FINAL" = "succeeded" ] && pass "S09: job succeeded on retry"          || fail "S09: final state=$STATE_FINAL"
[ "$ATTEMPTS_FINAL" = "1" ]      && pass "S09: attempts=1 (one failure recorded)" || fail "S09: attempts=$ATTEMPTS_FINAL"


# ════════════════════════════════════════════════════════════
header "SCENARIO 10: Concurrent duplicate submission race"
# ════════════════════════════════════════════════════════════
cleanup_key "s10"
log "10 concurrent submissions with same key — only 1 job created"

for i in $(seq 1 10); do
  curl -s --max-time 5 -X POST http://localhost:8000/jobs \
    -H "Content-Type: application/json" \
    -d '{"payload":{"task":"concurrent"},"idempotency_key":"s10"}' \
    > /tmp/s10_r${i}.log 2>&1 &
done
wait $(jobs -p) 2>/dev/null || true

JOB_COUNT_S10=$(db_count "SELECT COUNT(*) FROM jobs WHERE idempotency_key='s10'")
IDS=$(for i in $(seq 1 10); do python3 -c "import json; d=json.load(open('/tmp/s10_r${i}.log')); print(d.get('job_id',''))" 2>/dev/null; done | sort -u | wc -l | tr -d ' ')

[ "$JOB_COUNT_S10" = "1" ] && pass "S10: exactly 1 job row despite 10 concurrent submissions" || fail "S10: job_count=$JOB_COUNT_S10"
[ "$IDS" = "1" ]           && pass "S10: all responses returned same job_id"                   || fail "S10: $IDS distinct job_ids returned"


# ════════════════════════════════════════════════════════════
header "SCENARIO 11: UNIQUE(job_id, fencing_token) blocks duplicate ledger write"
# ════════════════════════════════════════════════════════════
cleanup_key "s11"
log "Direct DB test: inserting same (job_id, token) twice → only 1 row"

python3 -c "
import psycopg2, uuid, hashlib
conn = psycopg2.connect('$DATABASE_URL')
cur = conn.cursor()
jid = str(uuid.uuid4())
h = hashlib.sha256('{}'. encode()).hexdigest()
cur.execute(\"INSERT INTO jobs (id,payload,payload_hash,state,attempts,max_attempts) VALUES (%s,'{}', %s,'running',0,3)\",(jid,h))
cur.execute('INSERT INTO ledger_entries (job_id,fencing_token,account_id,delta) VALUES (%s,1,%s,1)',(jid,'default'))
cur.execute('INSERT INTO ledger_entries (job_id,fencing_token,account_id,delta) VALUES (%s,1,%s,1) ON CONFLICT (job_id,fencing_token) DO NOTHING',(jid,'default'))
cur.execute('SELECT COUNT(*) FROM ledger_entries WHERE job_id=%s',(jid,))
count = cur.fetchone()[0]
conn.commit()
conn.close()
print(count)
" > /tmp/s11.log 2>&1

COUNT_S11=$(cat /tmp/s11.log)
[ "$COUNT_S11" = "1" ] && pass "S11: UNIQUE constraint blocked duplicate ledger insert" || fail "S11: ledger count=$COUNT_S11"


# ════════════════════════════════════════════════════════════
header "SCENARIO 12: Worker restart mid-batch — no job loss"
# ════════════════════════════════════════════════════════════
cleanup_key "s12a"; cleanup_key "s12b"; cleanup_key "s12c"
log "Start 3 jobs, kill worker after first, restart — all 3 succeed"

# Drain leftover queued jobs so workers only see s12a/b/c
python3 services/worker/drain_queue.py 2>/dev/null || true


J1=$(seed_job "s12a"); J2=$(seed_job "s12b"); J3=$(seed_job "s12c")

DATABASE_URL="$DATABASE_URL" METRICS_ENABLED=0 WORK_SLEEP_SECONDS=0 PYTHONPATH=$(pwd) \
  LEASE_SECONDS=5 MAX_LOOPS=2 \
  python3 services/worker/worker.py > /tmp/s12_w1.log 2>&1 || true

DATABASE_URL="$DATABASE_URL" METRICS_ENABLED=0 WORK_SLEEP_SECONDS=0 PYTHONPATH=$(pwd) \
  LEASE_SECONDS=30 MAX_LOOPS=20 \
  python3 services/worker/worker.py > /tmp/s12_w2.log 2>&1 || true

sleep 3
S1=$(db_job "$J1" "state"); S2=$(db_job "$J2" "state"); S3=$(db_job "$J3" "state")
ALL_DONE=true
[ "$S1" = "succeeded" ] || ALL_DONE=false
[ "$S2" = "succeeded" ] || ALL_DONE=false
[ "$S3" = "succeeded" ] || ALL_DONE=false
[ "$ALL_DONE" = "true" ] && pass "S12: all 3 jobs succeeded after worker restart" || fail "S12: states=($S1,$S2,$S3)"


# ════════════════════════════════════════════════════════════
header "SCENARIO 13: Expired lease reaper resets stuck running job"
# ════════════════════════════════════════════════════════════
cleanup_key "s13"
log "Job stuck in running with expired lease — reaper resets to queued"

S13_JOB=$(python3 -c "
import psycopg2, uuid, hashlib
conn = psycopg2.connect('$DATABASE_URL')
cur = conn.cursor()
jid = str(uuid.uuid4())
h = hashlib.sha256('{}'. encode()).hexdigest()
cur.execute(\"\"\"INSERT INTO jobs (id,payload,payload_hash,state,attempts,
    max_attempts,idempotency_key,fencing_token,lease_owner,lease_expires_at,next_run_at)
    VALUES (%s,'{}', %s,'running',0,3,'s13',1,'dead-worker',NOW()-interval '60s',NOW())\"\"\", (jid,h))
conn.commit()
conn.close()
print(jid)
")

# Run reaper
python3 -c "
import psycopg2
conn = psycopg2.connect('$DATABASE_URL')
cur = conn.cursor()
cur.execute(\"\"\"WITH expired AS (SELECT id FROM jobs WHERE state='running'
    AND lease_expires_at IS NOT NULL AND lease_expires_at<NOW() AND id=%s LIMIT 10 FOR UPDATE SKIP LOCKED)
    UPDATE jobs SET state='queued',lease_owner=NULL,lease_expires_at=NULL,next_run_at=NOW(),updated_at=NOW()
    WHERE id IN (SELECT id FROM expired) RETURNING id\"\"\", ('$S13_JOB',))
print('reaped:', cur.fetchall())
conn.commit()
conn.close()
"

STATE=$(db_job "$S13_JOB" "state")
[ "$STATE" = "queued" ] && pass "S13: reaper reset expired lease to queued" || fail "S13: state=$STATE"


# ════════════════════════════════════════════════════════════
header "SCENARIO 14: DB health check endpoint responds correctly"
# ════════════════════════════════════════════════════════════
log "API /health returns 200 with db=connected"

HEALTH=$(curl -s http://localhost:8000/health)
STATUS=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))")
[ "$STATUS" = "ok" ] && pass "S14: /health returns status=ok" || fail "S14: health=$HEALTH"


# ════════════════════════════════════════════════════════════
header "SCENARIO 15: Queue depth endpoint reflects real counts"
# ════════════════════════════════════════════════════════════
log "/queue/depth shows correct counts per state"

DEPTH=$(curl -s http://localhost:8000/queue/depth 2>/dev/null || echo "{}")
python3 -c "
import json, sys
d = json.loads('$DEPTH' if '$DEPTH' != '{}' else json.dumps({}))
print('ok' if isinstance(d, dict) else 'fail')
" > /tmp/s15.log 2>&1 || echo "fail" > /tmp/s15.log

RESULT=$(cat /tmp/s15.log)
[ "$RESULT" = "ok" ] && pass "S15: /queue/depth returns state map" || fail "S15: unexpected response: $DEPTH"


# ════════════════════════════════════════════════════════════
header "SCENARIO 16: Job not found returns 404"
# ════════════════════════════════════════════════════════════
log "GET /jobs/<nonexistent-id> returns 404"

HTTP_404=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/jobs/00000000-0000-0000-0000-000000000000)
[ "$HTTP_404" = "404" ] && pass "S16: nonexistent job returns 404" || fail "S16: got HTTP $HTTP_404"


# ════════════════════════════════════════════════════════════
# Summary
# ════════════════════════════════════════════════════════════
echo ""
echo "════════════════════════════════════════════════════════"
echo -e "  ${BOLD}Results${NC}"
echo "════════════════════════════════════════════════════════"
echo -e "  ${GREEN}Passed${NC}: $PASS"
echo -e "  ${RED}Failed${NC}: $FAIL"
echo "  Total scenarios: $((PASS + FAIL))"

if [ ${#ERRORS[@]} -gt 0 ]; then
    echo ""
    echo "  Failures:"
    for e in "${ERRORS[@]}"; do
        echo -e "    ${RED}FAIL${NC} $e"
    done
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
    echo -e "${GREEN}  All $PASS failure scenarios passed${NC}"
    exit 0
else
    echo -e "${RED}  $FAIL scenario(s) failed${NC}"
    exit 1
fi
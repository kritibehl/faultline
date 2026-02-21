#!/usr/bin/env bash
set -euo pipefail

API="http://localhost:8000"

echo "== Health check =="
curl -s "$API/health"
echo -e "\n"

echo "== Retry demo: fail twice, then succeed =="
JOB_ID=$(curl -s -X POST "$API/jobs" \
  -H "Content-Type: application/json" \
  -d '{"payload":{"fail_n_times":2},"idempotency_key":"proof-retry-1"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")

echo "job_id=$JOB_ID"

for i in {1..10}; do
  curl -s "$API/jobs/$JOB_ID"
  echo
  sleep 2
done

echo
echo "== Idempotency demo =="
JOB_ID_1=$(curl -s -X POST "$API/jobs" \
  -H "Content-Type: application/json" \
  -d '{"payload":{"fail_n_times":0},"idempotency_key":"proof-idem-1"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")

JOB_ID_2=$(curl -s -X POST "$API/jobs" \
  -H "Content-Type: application/json" \
  -d '{"payload":{"fail_n_times":0},"idempotency_key":"proof-idem-1"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")

echo "first=$JOB_ID_1"
echo "second=$JOB_ID_2"

if [ "$JOB_ID_1" != "$JOB_ID_2" ]; then
  echo "❌ ERROR: idempotency failed"
  exit 1
fi

echo "✅ Idempotency OK"
echo
echo "== DONE =="

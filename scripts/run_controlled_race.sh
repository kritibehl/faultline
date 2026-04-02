#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

export DATABASE_URL="${DATABASE_URL:-postgresql://faultline:faultline@localhost:5432/faultline}"
export PYTHONUNBUFFERED=1
export LEASE_RACE_WAIT_SECONDS="${LEASE_RACE_WAIT_SECONDS:-7}"

echo "[faultline] running deterministic lease-race proof"
pytest -q tests/test_controlled_lease_race.py

latest="$(ls -t artifacts/races/*.json 2>/dev/null | head -n 1 || true)"
if [ -n "${latest}" ]; then
  echo "[faultline] latest artifact: ${latest}"
  python3 scripts/render_incident_timeline.py "${latest}"
  python3 scripts/explain_race.py "${latest}"
  python3 scripts/export_race_for_dettrace.py "${latest}"
fi

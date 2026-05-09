#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.." || exit 1
export PYTHONPATH="$(pwd)"

echo "== Replay validation =="
python scripts/validate_replays.py

echo
echo "== Benchmark report =="
python faultline_cli.py report

echo
echo "== Trace export =="
python scripts/export_trace_demo.py

echo
echo "== Metrics smoke test =="
python - <<'PY'
from metrics.prometheus_metrics import FaultlineMetrics
m = FaultlineMetrics()
m.stale_write_rejected_total = 1
m.lease_takeover_total = 1
print(m.render_prometheus())
PY

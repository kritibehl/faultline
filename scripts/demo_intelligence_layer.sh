#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.." || exit 1
export PYTHONPATH="$(pwd)"

echo "== Incident similarity =="
python intelligence/similarity.py

echo
echo "== Correctness score =="
python intelligence/correctness_score.py

echo
echo "== Release gate =="
python intelligence/release_gate.py

echo
echo "== Incident report =="
python intelligence/render_incident_report.py

echo
echo "== Benchmark trends =="
python intelligence/benchmark_trends.py

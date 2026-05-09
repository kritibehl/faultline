#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.." || exit 1
export PYTHONPATH="$(pwd)"

echo "== Export trace demo =="
python scripts/export_trace_demo.py

echo
echo "== Reconstruct timeline =="
python analysis/timeline/reconstruct_timeline.py

echo
echo "== Operator decision =="
python analysis/operator/decision_engine.py

echo
echo "== Tuning recommendation =="
python analysis/tuning/recommend.py

echo
echo "== Benchmark regression check =="
python analysis/benchmarks/regression_check.py

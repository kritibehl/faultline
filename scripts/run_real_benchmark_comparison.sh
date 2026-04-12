#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.." || exit 1
source .venv/bin/activate

export DATABASE_URL="${DATABASE_URL:-postgresql://faultline:faultline@localhost:5432/faultline}"
export PYTHONPATH="$(pwd)"

mkdir -p benchmarks/results

for rate in 5 10 20; do
  echo
  echo "=== Running Faultline benchmark at ${rate}% fault injection ==="
  FAULTLINE_FAULT_PCT="$rate" python benchmarks/faultline_harness.py

  echo
  echo "=== Running naive queue benchmark at ${rate}% fault injection ==="
  NAIVE_FAULT_PCT="$rate" python benchmarks/naive_queue_harness.py
done

echo
echo "=== Exporting comparison chart ==="
python benchmarks/export_comparison.py

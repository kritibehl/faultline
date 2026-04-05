#!/usr/bin/env bash
set -euo pipefail

export PYTHONPATH="${PYTHONPATH:-.}:."

python3 -m benchmarks.run_benchmarks
python3 -m benchmarks.compare_runs
python3 -m benchmarks.report_generator
python3 -m benchmarks.report_generator_extra

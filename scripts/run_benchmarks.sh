#!/usr/bin/env bash
set -euo pipefail

mkdir -p reports/benchmarks

python -m pytest tests -q | tee reports/benchmarks/test_summary.txt

cat > reports/benchmarks/validation_table.md <<'EOF'
# Faultline Validation Table

| Scenario | Runs | Duplicate Commits | Stale Commits Rejected | Recovery Outcome |
|---|---:|---:|---:|---|
| Healthy execution | TBD | TBD | TBD | TBD |
| Lease expiry mid-execution | TBD | TBD | TBD | TBD |
| Delayed stale completion | TBD | TBD | TBD | TBD |
| Partial partition | TBD | TBD | TBD | TBD |
| gRPC latency + heartbeat | TBD | TBD | TBD | TBD |
| Tool-call malformed output | TBD | TBD | TBD | TBD |
EOF

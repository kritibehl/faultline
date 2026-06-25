#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:-127.0.0.1}"
PORT="${2:-8088}"

echo "baseline_target=$TARGET"
echo "baseline_port=$PORT"

if nc -z "$TARGET" "$PORT" 2>/dev/null; then
  echo "status=reachable"
else
  echo "status=unreachable"
fi

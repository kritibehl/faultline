#!/usr/bin/env bash
set -euo pipefail

echo "== Process snapshot =="
ps aux | grep -E "faultline|python|go" | grep -v grep || true

echo
echo "== CPU / memory snapshot =="
top -l 1 | head -n 20 2>/dev/null || true

echo
echo "== Docker containers =="
docker ps 2>/dev/null || true

echo
echo "== Faultline ports =="
lsof -i :8088 2>/dev/null || true
lsof -i :5432 2>/dev/null || true

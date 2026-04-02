#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "[faultline] otel proof placeholder"
echo "Run your collector / Jaeger, then run controlled race, then capture:"
echo "submit -> claim -> execute -> complete"
echo "Store screenshots in docs/proofs/"

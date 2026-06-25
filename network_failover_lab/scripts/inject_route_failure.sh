#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:-127.0.0.1}"

echo "simulated_route_failure=true"
echo "target=$TARGET"
echo "note=this script documents route degradation simulation; no privileged route mutation is performed by default"

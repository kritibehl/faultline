#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:-127.0.0.1}"

echo "simulated_route_restore=true"
echo "target=$TARGET"
echo "recovery_status=restored"

#!/usr/bin/env bash
set -euo pipefail

echo "=== grpc latency profile ==="
toxiproxy-cli toxic add faultline-grpc -t latency -a latency=400

echo "=== grpc jitter profile ==="
toxiproxy-cli toxic add faultline-grpc -t latency -a latency=200 -a jitter=150

echo "=== grpc timeout / cut connection ==="
toxiproxy-cli toxic add faultline-grpc -t timeout -a timeout=1500

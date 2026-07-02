#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="${TMPDIR:-/tmp}/faultline-java-health"

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"

javac -d "$OUT_DIR"
src/main/java/faultline/health/HealthCheckClient.java
src/test/java/faultline/health/HealthCheckClientTest.java

java -cp "$OUT_DIR" faultline.health.HealthCheckClientTest

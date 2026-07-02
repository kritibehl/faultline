# Java Health Check Client

Small Java deployment-readiness client for Faultline.

## Capabilities

- HTTP health check
- timeout handling
- JSON response parsing
- non-zero exit code for unhealthy service
- simple CI-friendly test without external dependencies

## Run test

```bash
javac -d /tmp/faultline-java-health \
  src/main/java/faultline/health/HealthCheckClient.java \
  src/test/java/faultline/health/HealthCheckClientTest.java

java -cp /tmp/faultline-java-health faultline.health.HealthCheckClientTest
Safe claim

This is a small Java health-check client for deployment-readiness workflows. It is not a full Java service.

# Faultline Platform Walkthrough

Faultline includes platform-facing artifacts for backend infrastructure review.

## Go inspector service

Endpoints:

- `/health`
- `/leases`
- `/metrics`
- `/trace/export`

## Kubernetes and Helm

Artifacts:

- `k8s/`
- `helm/faultline/`

These include deployment manifests, service manifests, readiness/liveness probes, secrets examples, and Helm templates.

## Observability stack

Artifact:

- `observability/docker-compose.observability.yml`

Includes examples for:

- Prometheus
- Grafana
- Jaeger
- Loki

## Migrations

Artifact:

- `migrations/`

Includes Flyway-style schema migration examples for:

- jobs table
- ledger entries
- lease indexes
- retry/dead-letter fields

## k6 load test

Artifact:

- `load_tests/k6/`

Covers inspector API endpoints under concurrent HTTP traffic.

## OpenAPI

Artifact:

- `docs/openapi/go-inspector-openapi.yaml`

Documents the Go inspector API contract.

## Failure replay screenshot

Artifact:

- `docs/assets/failure_replay_screenshot.svg`

Shows stale-worker reconstruction across claim, takeover, commit, and rejection.

## Safe positioning

These are deployability, observability, and platform-readiness artifacts. They should not be described as production-scale operations or enterprise infrastructure deployment.

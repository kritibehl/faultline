# Faultline Inspector

Faultline Inspector is a Go-based operational utility for inspecting distributed worker lease state.

## Capabilities

- inspect worker leases
- detect expired leases
- estimate duplicate-risk exposure
- expose `/health` and `/metrics` endpoints
- validate PostgreSQL-backed execution state

## Endpoints

- `/health`
- `/metrics`

## Example

```bash
cd cmd/faultline-inspector
DATABASE_URL='postgresql://faultline:faultline@localhost:5432/faultline' go run .
In another terminal:

curl http://localhost:8088/health
curl http://localhost:8088/metrics
Use cases
distributed job systems
Temporal-style worker fleets
backend infrastructure debugging
stale-worker detection
operational lease validation

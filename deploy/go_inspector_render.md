# Deploy Faultline Inspector

Faultline Inspector is a small Go service exposing:

- `/`
- `/health`
- `/leases`
- `/metrics`
- `/trace/export`

## Local run

```bash
cd cmd/faultline-inspector
go run .
Docker run
docker build -f cmd/faultline-inspector/Dockerfile -t faultline-inspector .
docker run -p 8088:8088 faultline-inspector
Optional PostgreSQL-backed mode
docker run -p 8088:8088 \
  -e DATABASE_URL='postgresql://faultline:faultline@host.docker.internal:5432/faultline' \
  faultline-inspector

If DATABASE_URL is not set or unreachable, the service falls back to demo mode so reviewers can still see the dashboard and endpoints.

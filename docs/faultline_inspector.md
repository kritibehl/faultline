# Faultline Inspector

Faultline Inspector is a Go-based operational utility for inspecting distributed worker lease state.

Capabilities:
- inspect worker leases
- detect expired leases
- estimate duplicate-risk exposure
- expose /health and /metrics endpoints
- validate PostgreSQL-backed execution state

Endpoints:
- /health
- /metrics

Example:

```bash
curl http://localhost:8088/health
Use cases:

distributed job systems
Temporal-style worker fleets
backend infrastructure debugging
stale-worker detection
operational lease validation

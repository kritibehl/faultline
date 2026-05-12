# Go Inspector Walkthrough

Faultline includes a small Go backend service for operational inspection of worker leases and duplicate-risk state.

Location:

```text
cmd/faultline-inspector/
Run locally
cd cmd/faultline-inspector
go run .

The service starts on:

http://localhost:8088

If DATABASE_URL is set, the inspector reads PostgreSQL-backed job state.
If the database is unavailable, it falls back to demo mode so the endpoints remain reviewable.

Endpoints
/health

Returns lease-state and duplicate-risk summary.

curl http://localhost:8088/health

Sample output:

{
  "total_jobs": 200,
  "running_jobs": 3,
  "queued_jobs": 0,
  "failed_jobs": 0,
  "succeeded_jobs": 197,
  "expired_leases": 1,
  "potential_duplicate_risk": 1,
  "lease_risk": "medium",
  "safe_to_operate": true,
  "mode": "demo_no_database"
}
/leases

Returns the same lease inspection summary for worker-state review.

curl http://localhost:8088/leases
/metrics

Exports Prometheus-style runtime metrics.

curl http://localhost:8088/metrics

Sample output:

faultline_total_jobs 200
faultline_running_jobs 3
faultline_expired_leases_total 1
faultline_duplicate_risk_total 1
faultline_safe_to_operate 1
/trace/export

Exports a sample trace showing lease ownership transition and stale-worker rejection.

curl http://localhost:8088/trace/export

Trace phases:

claim_job
acquire_lease
lease_takeover
commit_result
reject_stale_write
What this proves

The Go inspector demonstrates:

backend service implementation in Go
HTTP health and metrics endpoints
lease-state inspection
duplicate-risk summary
trace export for stale-worker reconstruction
PostgreSQL-backed operational debugging path
Safe claim

This is a deployable Go inspector/demo service. It should not be described as production deployment or production-scale observability infrastructure.

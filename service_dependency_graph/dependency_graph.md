# Faultline Service Dependency Graph

## Worker service

```json
{
  "upstream": ["producer_api", "queue_runtime", "retry_scheduler"],
  "downstream": ["postgres", "outbox", "inspector", "metrics_exporter"]
}
Critical dependencies
Dependency	Reason
PostgreSQL	fencing-token validation and commit correctness
Outbox	replayable event delivery
Metrics exporter	operational visibility
Inspector	lease-state and duplicate-risk debugging
Failure behavior
PostgreSQL unavailable: pause unsafe commits or fail closed
Outbox unavailable: replay event delivery
Inspector unavailable: core correctness unaffected, debugging degraded
Metrics unavailable: correctness unaffected, observability degraded

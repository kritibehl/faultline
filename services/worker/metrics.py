"""
services/worker/metrics.py
Prometheus metrics for Faultline — counters, histograms, gauges.
"""
from prometheus_client import Counter, Histogram, Gauge

jobs_claimed = Counter("faultline_jobs_claimed_total", "Lease acquisitions")
jobs_succeeded = Counter("faultline_jobs_succeeded_total", "Successful commits")
jobs_retried = Counter("faultline_jobs_retried_total", "Retry scheduling events")
jobs_failed_perm = Counter("faultline_jobs_failed_total", "Permanent failures")
stale_commits_prevented = Counter("faultline_stale_commit_prevented_total", "Stale writes blocked")
reconciler_runs = Counter("faultline_reconciler_runs_total", "Reconciler invocations")
reconciler_converged = Counter("faultline_reconciler_converged_total", "Jobs converged by reconciler")

lease_acquisition_latency = Histogram(
    "faultline_lease_acquisition_latency_seconds",
    "Time to acquire lease",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)
job_execution_latency = Histogram(
    "faultline_job_execution_latency_seconds",
    "Claim to commit latency",
    buckets=[0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10, 30, 60],
)
retries_per_job = Histogram(
    "faultline_retries_per_job",
    "Retry count distribution",
    buckets=[0, 1, 2, 3, 4, 5, 10],
)

jobs_queued_gauge = Gauge("faultline_jobs_queued", "Current queued count")
jobs_running_gauge = Gauge("faultline_jobs_running", "Current running count")
jobs_succeeded_gauge = Gauge("faultline_jobs_succeeded_gauge", "Cumulative succeeded")
jobs_failed_gauge = Gauge("faultline_jobs_failed_gauge", "Cumulative failed")

def update_queue_gauges(database_url: str) -> None:
    import psycopg2
    try:
        with psycopg2.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT state, COUNT(*) FROM jobs GROUP BY state")
                counts = dict(cur.fetchall())
        jobs_queued_gauge.set(counts.get("queued", 0))
        jobs_running_gauge.set(counts.get("running", 0))
        jobs_succeeded_gauge.set(counts.get("succeeded", 0))
        jobs_failed_gauge.set(counts.get("failed", 0))
    except Exception:
        pass

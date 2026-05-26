from __future__ import annotations

from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import FastAPI, Response

app = FastAPI(title="Faultline Operational Metrics")

active_workers = Gauge(
    "faultline_active_workers",
    "Active worker count"
)

retries_per_second = Gauge(
    "faultline_retries_per_second",
    "Retry rate per second"
)

expired_leases = Gauge(
    "faultline_expired_leases",
    "Expired lease count"
)

queue_depth = Gauge(
    "faultline_queue_depth",
    "Current queue depth"
)

stale_worker_rejections = Counter(
    "faultline_stale_worker_rejections_total",
    "Stale-worker write rejections"
)

db_retry_count = Counter(
    "faultline_db_retry_total",
    "Database transaction retries"
)

@app.get("/metrics")
def metrics():
    active_workers.set(25)
    retries_per_second.set(1.8)
    expired_leases.set(3)
    queue_depth.set(42)

    stale_worker_rejections.inc(0)
    db_retry_count.inc(0)

    return Response(
        generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )

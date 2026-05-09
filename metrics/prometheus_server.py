from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi import FastAPI, Response

stale_write_rejected_total = Counter(
    "faultline_stale_write_rejected_total",
    "Stale writes rejected by fencing-token validation",
)

lease_takeover_total = Counter(
    "faultline_lease_takeover_total",
    "Lease takeovers after expiry",
)

retry_total = Counter(
    "faultline_retry_total",
    "Retries scheduled",
)

claim_latency_ms = Histogram(
    "faultline_claim_latency_ms",
    "Claim latency in milliseconds",
)

commit_latency_ms = Histogram(
    "faultline_commit_latency_ms",
    "Commit latency in milliseconds",
)

app = FastAPI(title="Faultline Metrics")

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

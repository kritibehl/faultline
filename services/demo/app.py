from fastapi import FastAPI
from pathlib import Path
import json

from metrics.prometheus_metrics import FaultlineMetrics

app = FastAPI(title="Faultline Demo API")

@app.get("/health")
def health():
    return {"status": "ok", "service": "faultline-demo"}

@app.get("/metrics")
def metrics():
    m = FaultlineMetrics()
    m.stale_write_rejected_total = 1
    m.lease_takeover_total = 1
    m.retry_total = 1
    m.observe_claim_latency(3.2)
    m.observe_commit_latency(4.8)
    return m.render_prometheus()

@app.get("/replays")
def replays():
    out = []
    for p in Path("replays").glob("*.json"):
        out.append(json.loads(p.read_text()))
    return {"replays": out}

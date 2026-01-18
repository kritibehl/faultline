from fastapi import FastAPI
from prometheus_client import Counter, generate_latest
from starlette.responses import Response

app = FastAPI()

requests_total = Counter(
    "faultline_api_requests_total",
    "Total API requests"
)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type="text/plain")

@app.middleware("http")
async def count_requests(request, call_next):
    requests_total.inc()
    return await call_next(request)

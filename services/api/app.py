import uuid
from datetime import datetime
from pydantic import BaseModel
from db import get_conn
from fastapi import FastAPI
from prometheus_client import Counter, generate_latest
from starlette.responses import Response

app = FastAPI()

class JobRequest(BaseModel):
    payload: dict
    idempotency_key: str | None = None


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


@app.post("/jobs")
def create_job(req: JobRequest):
    job_id = uuid.uuid4()

    with get_conn() as conn:
        with conn.cursor() as cur:
            if req.idempotency_key:
                cur.execute(
                    "SELECT id FROM jobs WHERE idempotency_key = %s",
                    (req.idempotency_key,)
                )
                row = cur.fetchone()
                if row:
                    return {"job_id": row[0]}

            cur.execute(
                """
                INSERT INTO jobs (id, idempotency_key, state, payload)
                VALUES (%s, %s, %s, %s)
                """,
                (job_id, req.idempotency_key, "queued", req.payload)
            )

    return {"job_id": job_id}

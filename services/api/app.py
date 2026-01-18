import uuid
import hashlib
from psycopg2.extras import Json

from fastapi import FastAPI
from pydantic import BaseModel
from prometheus_client import Counter, generate_latest
from starlette.responses import Response

from db import get_conn

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
    job_id = str(uuid.uuid4())

    payload_bytes = str(req.payload).encode("utf-8")
    payload_hash = hashlib.sha256(payload_bytes).hexdigest()

    with get_conn() as conn:
        with conn.cursor() as cur:
            if req.idempotency_key:
                cur.execute(
                    """
                    SELECT id, payload_hash
                    FROM jobs
                    WHERE idempotency_key = %s
                    """,
                    (req.idempotency_key,)
                )
                row = cur.fetchone()
                if row:
                    existing_id, existing_hash = row
                    if existing_hash != payload_hash:
                        return {"error": "Idempotency key reuse with different payload"}
                    return {"job_id": existing_id}

            cur.execute(
                """
                INSERT INTO jobs (id, idempotency_key, payload_hash, state, payload)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (job_id, req.idempotency_key, payload_hash, "queued", Json(req.payload))
            )

    return {"job_id": job_id}


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, state, attempts, max_attempts, last_error
                FROM jobs
                WHERE id = %s
                """,
                (job_id,)
            )
            row = cur.fetchone()
            if not row:
                return {"error": "not found"}

            return {
                "job_id": row[0],
                "state": row[1],
                "attempts": row[2],
                "max_attempts": row[3],
                "last_error": row[4],
            }

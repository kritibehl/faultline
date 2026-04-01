"""
services/api/app.py
────────────────────
Faultline HTTP API — deployed service entrypoint.

Uses raw psycopg2 (no ORM) for consistency with the worker layer.
PostgreSQL is the single source of truth — no external broker.
"""

import hashlib
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from services.common.tracing import init_tracing, get_tracer, input_fingerprint, inject_traceparent, start_span
from prometheus_client import Counter, generate_latest
from psycopg2.extras import Json
from pydantic import BaseModel
from starlette.responses import Response

from db import get_conn

init_tracing("faultline-api")
tracer = get_tracer("faultline.api")

app = FastAPI(title="Faultline", version="1.0.0")

# ── Metrics ───────────────────────────────────────────────────────────────────

requests_total = Counter("faultline_api_requests_total", "Total HTTP requests")
jobs_submitted = Counter("faultline_api_jobs_submitted_total", "Jobs submitted")
jobs_duplicate = Counter("faultline_api_duplicate_rejected_total", "Idempotent returns")


# ── Models ────────────────────────────────────────────────────────────────────

class JobRequest(BaseModel):
    payload: dict
    idempotency_key: str | None = None


# ── Middleware ────────────────────────────────────────────────────────────────

@app.middleware("http")
async def count_requests(request, call_next):
    requests_total.inc()
    return await call_next(request)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Liveness check + DB connectivity probe."""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return {"status": "ok", "db": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"DB unavailable: {e}")


@app.get("/metrics")
def metrics():
    """Prometheus scrape endpoint."""
    return Response(generate_latest(), media_type="text/plain")


@app.post("/jobs", status_code=201)
def create_job(req: JobRequest):
    """
    Enqueue a new job.

    Idempotency: if idempotency_key is provided, duplicate submissions
    return the existing job (200) rather than creating a new one.
    Payload hash mismatch on the same key returns 409.
    """
    job_id = str(uuid.uuid4())
    payload_hash = hashlib.sha256(str(req.payload).encode()).hexdigest()

    with get_conn() as conn:
        with conn.cursor() as cur:

            # Idempotency check
            if req.idempotency_key:
                cur.execute(
                    "SELECT id, payload_hash FROM jobs WHERE idempotency_key = %s",
                    (req.idempotency_key,),
                )
                row = cur.fetchone()
                if row:
                    existing_id, existing_hash = row
                    if existing_hash != payload_hash:
                        raise HTTPException(
                            status_code=409,
                            detail="Idempotency key reused with different payload",
                        )
                    jobs_duplicate.inc()
                    return {"job_id": existing_id, "status": "existing"}

            cur.execute(
                """
                INSERT INTO jobs (id, idempotency_key, payload_hash, state, payload)
                VALUES (%s, %s, %s, 'queued', %s)
                """,
                (job_id, req.idempotency_key, payload_hash, Json(req.payload)),
            )

    jobs_submitted.inc()
    return {"job_id": job_id, "status": "queued"}


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    """Fetch current state of a job by ID."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, state, attempts, max_attempts,
                       fencing_token, last_error, created_at, updated_at
                FROM jobs WHERE id = %s
                """,
                (job_id,),
            )
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": row[0],
        "state": row[1],
        "attempts": row[2],
        "max_attempts": row[3],
        "fencing_token": row[4],
        "last_error": row[5],
        "created_at": str(row[6]),
        "updated_at": str(row[7]),
    }


@app.get("/queue/depth")
def queue_depth():
    """Current count of jobs per state — useful for backlog monitoring."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT state, COUNT(*) FROM jobs GROUP BY state")
            rows = cur.fetchall()
    return {row[0]: row[1] for row in rows}
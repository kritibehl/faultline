"""
api/routes/jobs.py
───────────────────
Job submission and status routes.

PostgreSQL is the source of truth. No Redis or external broker dependency —
the job row itself is the durable queue entry. Workers poll directly via
FOR UPDATE SKIP LOCKED.

Idempotency
───────────
POST /jobs accepts an optional idempotency_key. If a job with that key
already exists, the existing job is returned (200) rather than creating
a duplicate. This prevents double-submission from retrying clients.
"""

import uuid
import hashlib

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from api.db.session import get_db
from api.db.models import Job
from api.schemas.job import JobCreate, JobCreated
from common.states import JobState
from common.config import MAX_ATTEMPTS_DEFAULT

router = APIRouter()


def _payload_hash(payload: dict) -> str:
    return hashlib.sha256(str(payload).encode()).hexdigest()


@router.get("/health")
def health(db: Session = Depends(get_db)):
    """Liveness + DB connectivity check."""
    try:
        db.execute("SELECT 1")
        return {"status": "ok", "db": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"DB unavailable: {e}")


@router.post("/jobs", response_model=JobCreated, status_code=201)
def submit_job(body: JobCreate, db: Session = Depends(get_db)):
    """
    Enqueue a new job.

    If idempotency_key is provided and a job with that key already exists:
      - Same payload hash → return existing job (idempotent, 200)
      - Different payload  → 409 Conflict

    If no idempotency_key: always creates a new job.
    """
    payload_hash = _payload_hash(body.payload)

    # Check idempotency before inserting
    if body.idempotency_key:
        existing = db.query(Job).filter_by(idempotency_key=body.idempotency_key).first()
        if existing:
            if existing.payload_hash != payload_hash:
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency key reused with different payload",
                )
            return JobCreated(id=existing.id, state=existing.state)

    job = Job(
        id=uuid.uuid4(),
        type=body.type,
        payload=body.payload,
        payload_hash=payload_hash,
        idempotency_key=body.idempotency_key,
        state=JobState.QUEUED.value,
        max_attempts=MAX_ATTEMPTS_DEFAULT,
    )

    try:
        db.add(job)
        db.commit()
    except IntegrityError:
        # Race: another request inserted the same idempotency_key concurrently.
        db.rollback()
        existing = db.query(Job).filter_by(idempotency_key=body.idempotency_key).first()
        if existing:
            return JobCreated(id=existing.id, state=existing.state)
        raise HTTPException(status_code=500, detail="Unexpected integrity error")

    return JobCreated(id=job.id, state=job.state)


@router.get("/jobs/{job_id}", response_model=None)
def get_job(job_id: str, db: Session = Depends(get_db)):
    """Return current state of a job."""
    job = db.query(Job).filter_by(id=job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": str(job.id),
        "state": job.state,
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "last_error": job.last_error,
    }
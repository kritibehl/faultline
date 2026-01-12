import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from redis import Redis

from api.db.session import get_db
from api.db.models import Job
from api.schemas.job import JobCreate, JobCreated
from common.states import JobState
from common.config import REDIS_URL, STREAM_KEY, MAX_ATTEMPTS_DEFAULT

router = APIRouter()

def redis_client() -> Redis:
    return Redis.from_url(REDIS_URL, decode_responses=True)

@router.post("/jobs", response_model=JobCreated)
def submit_job(body: JobCreate, db: Session = Depends(get_db)):
    job = Job(
        id=uuid.uuid4(),
        type=body.type,
        payload=body.payload,
        state=JobState.QUEUED.value,
        max_attempts=MAX_ATTEMPTS_DEFAULT,
    )
    db.add(job)
    db.commit()

    # Enqueue after DB commit: Postgres is truth, Redis is coordination
    r = redis_client()
    try:
        r.xadd(STREAM_KEY, {"job_id": str(job.id)})
    except Exception as e:
        # IMPORTANT: the job remains durable in DB for recovery/re-enqueue later
        raise HTTPException(status_code=503, detail=f"Queue unavailable: {e}")

    return JobCreated(id=job.id, state=job.state)

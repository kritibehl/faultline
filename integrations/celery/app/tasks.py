from __future__ import annotations

import os
import time

from celery import Celery

from app.db import (
    fenced_commit,
    next_token,
    record_attempt,
    unsafe_commit,
)


BROKER_URL = os.getenv("BROKER_URL", "redis://redis:6379/0")
WORKER_NAME = os.getenv("WORKER_NAME", "unknown-worker")


app = Celery(
    "faultline_celery_demo",
    broker=BROKER_URL,
)

app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_transport_options={
        "visibility_timeout": 6,
        "unacked_restore_interval": 1,
        "unacked_restore_throttle": 1,
    },
    task_serializer="json",
    accept_content=["json"],
)


@app.task(
    bind=True,
    name="faultline.process_payment",
    acks_late=True,
)
def process_payment(
    self,
    job_id: str,
    amount: int,
    mode: str,
):
    token = next_token(job_id)

    record_attempt(
        job_id,
        WORKER_NAME,
        token,
        "delivery_started",
    )

    print(
        f"DELIVERY job={job_id} "
        f"worker={WORKER_NAME} "
        f"token={token} "
        f"mode={mode}",
        flush=True,
    )

    # The first ownership generation intentionally pauses in a
    # dangerous pre-commit window. Faultline's orchestrator will
    # SIGSTOP/pause the Worker A container while it is here.
    if token == 1:
        record_attempt(
            job_id,
            WORKER_NAME,
            token,
            "ready_to_commit",
        )

        print(
            f"READY_TO_COMMIT job={job_id} "
            f"worker={WORKER_NAME} token={token}",
            flush=True,
        )

        time.sleep(15)

    if mode == "unsafe":
        committed = unsafe_commit(
            job_id,
            WORKER_NAME,
            token,
            amount,
        )
    elif mode == "fenced":
        committed = fenced_commit(
            job_id,
            WORKER_NAME,
            token,
            amount,
        )
    else:
        raise ValueError(f"unsupported mode: {mode}")

    phase = "commit_accepted" if committed else "commit_rejected"

    record_attempt(
        job_id,
        WORKER_NAME,
        token,
        phase,
    )

    print(
        f"{phase.upper()} job={job_id} "
        f"worker={WORKER_NAME} token={token}",
        flush=True,
    )

    return {
        "job_id": job_id,
        "worker": WORKER_NAME,
        "token": token,
        "committed": committed,
    }

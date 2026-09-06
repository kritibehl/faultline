from __future__ import annotations

import os
import time

from celery import Celery

from app.db import (
    fenced_commit,
    idempotent_commit,
    next_token,
    record_attempt,
    unsafe_commit,
)


BROKER_URL = os.getenv(
    "BROKER_URL",
    "redis://redis:6379/0",
)

WORKER_NAME = os.getenv(
    "WORKER_NAME",
    "unknown-worker",
)


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
    window: str = "pre-commit",
):
    if window not in {
        "pre-commit",
        "post-commit",
    }:
        raise ValueError(
            f"unsupported window: {window}"
        )

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
        f"mode={mode} "
        f"window={window}",
        flush=True,
    )

    if token == 1 and window == "pre-commit":
        record_attempt(
            job_id,
            WORKER_NAME,
            token,
            "ready_to_commit",
        )

        print(
            f"READY_TO_COMMIT job={job_id} "
            f"worker={WORKER_NAME} "
            f"token={token}",
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

    elif mode == "idempotent":
        committed = idempotent_commit(
            job_id,
            WORKER_NAME,
            token,
            amount,
        )

    else:
        raise ValueError(
            f"unsupported mode: {mode}"
        )

    if committed:
        phase = "commit_accepted"

    elif mode == "idempotent":
        phase = "duplicate_suppressed"

    else:
        phase = "commit_rejected"

    record_attempt(
        job_id,
        WORKER_NAME,
        token,
        phase,
    )

    print(
        f"{phase.upper()} job={job_id} "
        f"worker={WORKER_NAME} "
        f"token={token}",
        flush=True,
    )

    if token == 1 and window == "post-commit":
        record_attempt(
            job_id,
            WORKER_NAME,
            token,
            "ready_after_commit",
        )

        print(
            f"READY_AFTER_COMMIT job={job_id} "
            f"worker={WORKER_NAME} "
            f"token={token}",
            flush=True,
        )

        time.sleep(15)

        record_attempt(
            job_id,
            WORKER_NAME,
            token,
            "post_commit_window_exit",
        )

        print(
            f"POST_COMMIT_WINDOW_EXIT job={job_id} "
            f"worker={WORKER_NAME} "
            f"token={token}",
            flush=True,
        )

    return {
        "job_id": job_id,
        "worker": WORKER_NAME,
        "token": token,
        "committed": committed,
        "window": window,
    }

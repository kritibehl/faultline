from __future__ import annotations

import json
import os
import time
import urllib.request

from celery import Celery

from app.db import (
    fenced_commit,
    next_token,
    record_attempt,
    unsafe_commit,
)


BROKER_URL = os.getenv(
    "BROKER_URL",
    "redis://redis:6379/0",
)

CHARGE_SERVICE_URL = os.getenv(
    "CHARGE_SERVICE_URL",
    "http://charge-service:8080",
)

WORKER_NAME = os.getenv(
    "WORKER_NAME",
    "unknown-worker",
)


STRATEGIES = {
    "naive",
    "fencing",
    "idempotency",
    "fencing-idempotency",
}


app = Celery(
    "faultline_ambiguous_demo",
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


def uses_remote_idempotency(
    strategy: str,
) -> bool:
    return strategy in {
        "idempotency",
        "fencing-idempotency",
    }


def uses_local_fencing(
    strategy: str,
) -> bool:
    return strategy in {
        "fencing",
        "fencing-idempotency",
    }


def call_charge_service(
    *,
    job_id: str,
    amount: int,
    token: int,
    strategy: str,
    drop_response: bool,
) -> dict[str, object]:
    remote_idempotent = (
        uses_remote_idempotency(
            strategy,
        )
    )

    endpoint = (
        "/charge-idempotent"
        if remote_idempotent
        else "/charge"
    )

    payload: dict[str, object] = {
        "job_id": job_id,
        "amount": amount,
    }

    if remote_idempotent:
        payload["idempotency_key"] = (
            job_id
        )

    headers = {
        "Content-Type":
            "application/json",
        "X-Faultline-Worker":
            WORKER_NAME,
        "X-Faultline-Token":
            str(token),
    }

    if uses_local_fencing(
        strategy
    ):
        headers[
            "X-Faultline-Fencing"
        ] = "enabled"

    if drop_response:
        headers[
            "X-Faultline-Drop-Response"
        ] = "after-commit"

    request = urllib.request.Request(
        CHARGE_SERVICE_URL + endpoint,
        data=json.dumps(payload).encode(
            "utf-8"
        ),
        headers=headers,
        method="POST",
    )

    with urllib.request.urlopen(
        request,
        timeout=30,
    ) as response:
        return json.loads(
            response.read().decode(
                "utf-8"
            )
        )


@app.task(
    bind=True,
    name="faultline.process_remote_charge",
    acks_late=True,
)
def process_remote_charge(
    self,
    job_id: str,
    amount: int,
    strategy: str,
):
    if strategy not in STRATEGIES:
        raise ValueError(
            f"unsupported strategy: "
            f"{strategy}"
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
        f"strategy={strategy}",
        flush=True,
    )

    record_attempt(
        job_id,
        WORKER_NAME,
        token,
        "effect_started",
    )

    print(
        f"EFFECT_STARTED job={job_id} "
        f"worker={WORKER_NAME} "
        f"token={token}",
        flush=True,
    )

    try:
        result = call_charge_service(
            job_id=job_id,
            amount=amount,
            token=token,
            strategy=strategy,
            drop_response=(
                token == 1
            ),
        )

    except Exception as exc:
        record_attempt(
            job_id,
            WORKER_NAME,
            token,
            "effect_result_unknown",
        )

        print(
            f"EFFECT_RESULT_UNKNOWN "
            f"job={job_id} "
            f"worker={WORKER_NAME} "
            f"token={token} "
            f"error={type(exc).__name__}",
            flush=True,
        )

        if token == 1:
            time.sleep(15)

        raise

    record_attempt(
        job_id,
        WORKER_NAME,
        token,
        "effect_result_observed",
    )

    print(
        f"REMOTE_EFFECT_OBSERVED "
        f"job={job_id} "
        f"worker={WORKER_NAME} "
        f"token={token} "
        f"duplicate_suppressed="
        f"{int(bool(result.get('duplicate_suppressed')))}",
        flush=True,
    )

    if uses_local_fencing(
        strategy
    ):
        committed = fenced_commit(
            job_id,
            WORKER_NAME,
            token,
            amount,
        )
    else:
        committed = unsafe_commit(
            job_id,
            WORKER_NAME,
            token,
            amount,
        )

    phase = (
        "local_commit_accepted"
        if committed
        else "local_commit_rejected"
    )

    record_attempt(
        job_id,
        WORKER_NAME,
        token,
        phase,
    )

    print(
        f"{phase.upper()} "
        f"job={job_id} "
        f"worker={WORKER_NAME} "
        f"token={token}",
        flush=True,
    )

    return {
        "job_id": job_id,
        "worker": WORKER_NAME,
        "token": token,
        "strategy": strategy,
        "remote_result": result,
        "local_committed": committed,
    }

from __future__ import annotations

import argparse
import os
import uuid

from celery import Celery


BROKER_URL = os.getenv(
    "BROKER_URL",
    "redis://redis:6379/0",
)


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--strategy",
        choices=[
            "naive",
            "fencing",
            "idempotency",
            "fencing-idempotency",
        ],
        required=True,
    )

    parser.add_argument(
        "--job-id",
        default=None,
    )

    args = parser.parse_args()

    job_id = (
        args.job_id
        or "ambiguous-"
        + uuid.uuid4().hex[:8]
    )

    app = Celery(
        "faultline_ambiguous_submitter",
        broker=BROKER_URL,
    )

    result = app.send_task(
        "faultline.process_remote_charge",
        args=[
            job_id,
            5000,
            args.strategy,
        ],
    )

    print(job_id)
    print(result.id)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import os
import uuid

from celery import Celery


BROKER_URL = os.getenv("BROKER_URL", "redis://redis:6379/0")


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--mode",
        choices=["unsafe", "fenced"],
        required=True,
    )

    parser.add_argument(
        "--job-id",
        default=None,
    )

    args = parser.parse_args()

    job_id = args.job_id or f"payment-{uuid.uuid4().hex[:8]}"

    app = Celery(
        "faultline_submitter",
        broker=BROKER_URL,
    )

    result = app.send_task(
        "faultline.process_payment",
        args=[
            job_id,
            100,
            args.mode,
        ],
    )

    print(job_id)
    print(result.id)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

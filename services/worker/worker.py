import os
import time
import uuid
from datetime import datetime, timedelta

import psycopg2
from prometheus_client import Counter, start_http_server

DATABASE_URL = os.environ["DATABASE_URL"]
WORKER_ID = str(uuid.uuid4())
LEASE_SECONDS = 30

heartbeat = Counter(
    "faultline_worker_heartbeat_total",
    "Worker heartbeat ticks",
)

jobs_claimed = Counter(
    "faultline_jobs_claimed_total",
    "Jobs claimed by worker",
)

jobs_succeeded = Counter(
    "faultline_jobs_succeeded_total",
    "Jobs marked succeeded by worker",
)


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def claim_one_job(cur):
    lease_until = datetime.utcnow() + timedelta(seconds=LEASE_SECONDS)
    cur.execute(
        """
        UPDATE jobs
        SET
            state = 'running',
            lease_owner = %s,
            lease_expires_at = %s,
            updated_at = NOW()
        WHERE id = (
            SELECT id
            FROM jobs
            WHERE state = 'queued'
               OR (state = 'running' AND lease_expires_at < NOW())
            ORDER BY created_at
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        RETURNING id
        """,
        (WORKER_ID, lease_until),
    )
    row = cur.fetchone()
    return row[0] if row else None


def mark_succeeded(cur, job_id):
    cur.execute(
        """
        UPDATE jobs
        SET
            state = 'succeeded',
            lease_owner = NULL,
            lease_expires_at = NULL,
            updated_at = NOW()
        WHERE id = %s
        """,
        (job_id,),
    )


if __name__ == "__main__":
    start_http_server(8000)

    while True:
        heartbeat.inc()

        with get_conn() as conn:
            with conn.cursor() as cur:
                job_id = claim_one_job(cur)
                if job_id:
                    jobs_claimed.inc()

                    # Simulate work (we'll replace with real execution later)
                    time.sleep(2)

                    mark_succeeded(cur, job_id)
                    jobs_succeeded.inc()

        time.sleep(2)

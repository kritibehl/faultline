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

retries_total = Counter(
    "faultline_retries_total",
    "Total job retries scheduled",
)

jobs_failed = Counter(
    "faultline_jobs_failed_total",
    "Total jobs marked failed",
)


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def wait_for_schema(timeout_seconds=60):
    """
    Block worker startup until the jobs table exists.
    Prevents crash loops on cold start before migrations run.
    """
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM jobs LIMIT 1;")
            return
        except Exception:
            time.sleep(2)
    raise RuntimeError("schema not ready after waiting")


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
            WHERE (
                    state = 'queued'
                AND (next_run_at IS NULL OR next_run_at <= NOW())
            )
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


def get_fail_n_times(payload):
    if isinstance(payload, dict) and "fail_n_times" in payload:
        try:
            return int(payload["fail_n_times"])
        except Exception:
            return 0
    return 0


def get_job(cur, job_id):
    cur.execute(
        """
        SELECT payload, attempts, max_attempts
        FROM jobs
        WHERE id = %s
        """,
        (job_id,),
    )
    row = cur.fetchone()
    if not row:
        return None, 0, 5
    return row[0], int(row[1] or 0), int(row[2] or 5)


def mark_succeeded(cur, job_id):
    cur.execute(
        """
        UPDATE jobs
        SET
            state = 'succeeded',
            lease_owner = NULL,
            lease_expires_at = NULL,
            next_run_at = NULL,
            updated_at = NOW()
        WHERE id = %s
        """,
        (job_id,),
    )


def schedule_retry(cur, job_id, attempts, delay_seconds, error_msg):
    next_run = datetime.utcnow() + timedelta(seconds=delay_seconds)
    cur.execute(
        """
        UPDATE jobs
        SET
            state = 'queued',
            attempts = %s,
            last_error = %s,
            lease_owner = NULL,
            lease_expires_at = NULL,
            next_run_at = %s,
            updated_at = NOW()
        WHERE id = %s
        """,
        (attempts, error_msg, next_run, job_id),
    )


def mark_failed(cur, job_id, attempts, error_msg):
    cur.execute(
        """
        UPDATE jobs
        SET
            state = 'failed',
            attempts = %s,
            last_error = %s,
            lease_owner = NULL,
            lease_expires_at = NULL,
            next_run_at = NULL,
            updated_at = NOW()
        WHERE id = %s
        """,
        (attempts, error_msg, job_id),
    )


if __name__ == "__main__":
    start_http_server(8000)

    # Ensure schema exists before processing jobs
    wait_for_schema()

    while True:
        heartbeat.inc()

        with get_conn() as conn:
            with conn.cursor() as cur:
                job_id = claim_one_job(cur)
                if job_id:
                    jobs_claimed.inc()

                    payload, attempts, max_attempts = get_job(cur, job_id)

                    try:
                        # Deterministic failure simulation: fail first N times
                        fail_n = get_fail_n_times(payload)
                        if attempts < fail_n:
                            raise RuntimeError(
                                f"simulated failure (attempt {attempts + 1}/{fail_n})"
                            )

                        # Simulated work
                        time.sleep(2)
                        mark_succeeded(cur, job_id)
                        jobs_succeeded.inc()

                    except Exception as e:
                        new_attempts = attempts + 1
                        msg = str(e)

                        if new_attempts < max_attempts:
                            delay = min(30, 2 ** max(1, new_attempts))
                            schedule_retry(cur, job_id, new_attempts, delay, msg)
                            retries_total.inc()
                        else:
                            mark_failed(cur, job_id, new_attempts, msg)
                            jobs_failed.inc()

        time.sleep(2)

import os
import time
import uuid
import json
from datetime import datetime, timedelta

import psycopg2
from psycopg2 import OperationalError
from prometheus_client import Counter, start_http_server

DATABASE_URL = os.environ["DATABASE_URL"]
WORKER_ID = str(uuid.uuid4())
LEASE_SECONDS = 30

CRASH_AT = os.getenv("CRASH_AT")  # after_lease_acquire | mid_execute | before_commit | after_commit
CLOCK_SKEW_MS = int(os.getenv("CLOCK_SKEW_MS", "0"))


# -------------------------
# Clock Abstraction
# -------------------------

class Clock:
    def now(self):
        return datetime.utcnow()


class SkewedClock(Clock):
    def __init__(self, offset_ms):
        self.offset = timedelta(milliseconds=offset_ms)

    def now(self):
        return datetime.utcnow() + self.offset


clock = SkewedClock(CLOCK_SKEW_MS) if CLOCK_SKEW_MS else Clock()


# -------------------------
# Logging
# -------------------------

def log_event(event, **fields):
    payload = {
        "event": event,
        "worker_id": WORKER_ID,
        "ts": datetime.utcnow().isoformat(),
        **fields,
    }
    print(json.dumps(payload), flush=True)


def maybe_crash(point):
    if CRASH_AT == point:
        log_event("crash_injected", point=point)
        os._exit(137)


# -------------------------
# Metrics
# -------------------------

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
    lease_until = clock.now() + timedelta(seconds=LEASE_SECONDS)

    cur.execute(
        """
        UPDATE jobs
        SET
            state = 'running',
            lease_owner = %s,
            lease_expires_at = %s,
            fencing_token = fencing_token + 1,
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
        RETURNING id, fencing_token
        """,
        (WORKER_ID, lease_until),
    )

    row = cur.fetchone()

    if row:
        job_id, token = row[0], int(row[1])
        log_event("lease_acquired", job_id=job_id, token=token)
        maybe_crash("after_lease_acquire")
        return job_id, token

    return None, None


def assert_fence(cur, job_id, token):
    cur.execute(
        """
        SELECT fencing_token, lease_expires_at
        FROM jobs
        WHERE id = %s
        """,
        (job_id,),
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError("job_missing")

    current_token, lease_expires_at = int(row[0]), row[1]

    if token != current_token:
        log_event("stale_write_blocked", job_id=job_id, stale_token=token, current_token=current_token)
        raise RuntimeError("stale_token")

    cur.execute("SELECT NOW()")
    now_db = cur.fetchone()[0]

    if lease_expires_at and lease_expires_at < now_db:
        log_event("stale_write_blocked", job_id=job_id, stale_token=token, reason="lease_expired")
        raise RuntimeError("lease_expired")


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


def mark_succeeded(cur, job_id, token):
    cur.execute(
        """
        SELECT fencing_token
        FROM jobs
        WHERE id = %s
        FOR UPDATE
        """,
        (job_id,),
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError("job_missing")

    current_token = int(row[0])
    if token != current_token:
        raise RuntimeError("stale_token")

    account_id = "default"
    delta = 1

    maybe_crash("before_commit")

    cur.execute(
        """
        INSERT INTO ledger_entries (job_id, fencing_token, account_id, delta)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (job_id, fencing_token) DO NOTHING
        """,
        (job_id, token, account_id, delta),
    )

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
          AND EXISTS (
            SELECT 1 FROM ledger_entries
            WHERE job_id = %s
              AND fencing_token = %s
          )
        """,
        (job_id, job_id, token),
    )

    maybe_crash("after_commit")


def schedule_retry(cur, job_id, attempts, delay_seconds, error_msg):
    next_run = clock.now() + timedelta(seconds=delay_seconds)

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
    wait_for_schema()

    while True:
        heartbeat.inc()

        try:
            with get_conn() as conn:
                with conn.cursor() as cur:

                    job_id, token = claim_one_job(cur)

                    if job_id:
                        jobs_claimed.inc()

                        payload, attempts, max_attempts = get_job(cur, job_id)

                        assert_fence(cur, job_id, token)

                        try:
                            fail_n = get_fail_n_times(payload)
                            if attempts < fail_n:
                                raise RuntimeError("simulated_failure")

                            log_event("execution_started", job_id=job_id, token=token)

                            maybe_crash("mid_execute")
                            time.sleep(2)

                            assert_fence(cur, job_id, token)

                            mark_succeeded(cur, job_id, token)
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

        except OperationalError:
            time.sleep(2)

        time.sleep(2)
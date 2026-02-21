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

BARRIER_WAIT = os.getenv("BARRIER_WAIT")
BARRIER_OPEN = os.getenv("BARRIER_OPEN")
BARRIER_TIMEOUT_S = int(os.getenv("BARRIER_TIMEOUT_S", "30"))


# =============================
# Clock Abstraction
# =============================

class Clock:
    def now(self):
        return datetime.utcnow()


class SkewedClock(Clock):
    def __init__(self, offset_ms):
        self.offset = timedelta(milliseconds=offset_ms)

    def now(self):
        return datetime.utcnow() + self.offset


clock = SkewedClock(CLOCK_SKEW_MS) if CLOCK_SKEW_MS else Clock()


# =============================
# Logging
# =============================

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


# =============================
# Barrier Helpers
# =============================

def open_barrier(cur, name):
    cur.execute(
        "INSERT INTO barriers(name) VALUES (%s) ON CONFLICT DO NOTHING",
        (name,),
    )


def wait_barrier(cur, name, timeout_s):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        cur.execute("SELECT 1 FROM barriers WHERE name=%s", (name,))
        if cur.fetchone():
            return True
        time.sleep(0.2)
    return False


def maybe_barrier(cur, point):
    if BARRIER_OPEN == point:
        log_event("barrier_open", name=point)
        open_barrier(cur, point)

    if BARRIER_WAIT == point:
        log_event("barrier_wait", name=point)
        ok = wait_barrier(cur, point, BARRIER_TIMEOUT_S)
        if not ok:
            raise RuntimeError(f"barrier_timeout {point}")


# =============================
# Metrics
# =============================

heartbeat = Counter("faultline_worker_heartbeat_total", "Worker heartbeat ticks")
jobs_claimed = Counter("faultline_jobs_claimed_total", "Jobs claimed by worker")
jobs_succeeded = Counter("faultline_jobs_succeeded_total", "Jobs marked succeeded by worker")
retries_total = Counter("faultline_retries_total", "Total job retries scheduled")
jobs_failed = Counter("faultline_jobs_failed_total", "Total jobs marked failed")


# =============================
# DB Helpers
# =============================

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


# =============================
# Lease Claim
# =============================

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

        maybe_barrier(cur, "after_lease_acquire")
        maybe_crash("after_lease_acquire")

        return job_id, token

    return None, None


# =============================
# Fence Enforcement
# =============================

def assert_fence(cur, job_id, token):
    cur.execute(
        "SELECT fencing_token, lease_expires_at FROM jobs WHERE id = %s",
        (job_id,),
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError("job_missing")

    current_token, lease_expires_at = int(row[0]), row[1]

    if token != current_token:
        log_event(
            "stale_write_blocked",
            job_id=job_id,
            stale_token=token,
            current_token=current_token,
        )
        raise RuntimeError("stale_token")

    cur.execute("SELECT NOW()")
    now_db = cur.fetchone()[0]

    if lease_expires_at and lease_expires_at < now_db:
        raise RuntimeError("lease_expired")


# =============================
# Apply Path
# =============================

def mark_succeeded(cur, job_id, token):
    cur.execute(
        "SELECT fencing_token FROM jobs WHERE id = %s FOR UPDATE",
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
        SET state='succeeded',
            lease_owner=NULL,
            lease_expires_at=NULL,
            next_run_at=NULL,
            updated_at=NOW()
        WHERE id=%s
          AND EXISTS (
              SELECT 1 FROM ledger_entries
              WHERE job_id=%s AND fencing_token=%s
          )
        """,
        (job_id, job_id, token),
    )

    maybe_crash("after_commit")


# =============================
# Main Loop
# =============================

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

                        assert_fence(cur, job_id, token)

                        log_event("execution_started", job_id=job_id, token=token)

                        maybe_crash("mid_execute")
                        time.sleep(2)

                        assert_fence(cur, job_id, token)

                        mark_succeeded(cur, job_id, token)
                        jobs_succeeded.inc()

        except OperationalError:
            time.sleep(2)

        time.sleep(2)
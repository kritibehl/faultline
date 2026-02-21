import os
import time
import uuid
import json
from datetime import datetime, timedelta

import psycopg2
from psycopg2 import OperationalError
from prometheus_client import Counter, start_http_server


# ============================================================
# Environment
# ============================================================

DATABASE_URL = os.environ["DATABASE_URL"]
WORKER_ID = str(uuid.uuid4())

LEASE_SECONDS = int(os.getenv("LEASE_SECONDS", "30"))
CRASH_AT = os.getenv("CRASH_AT")
CLOCK_SKEW_MS = int(os.getenv("CLOCK_SKEW_MS", "0"))

BARRIER_WAIT = os.getenv("BARRIER_WAIT")
BARRIER_OPEN = os.getenv("BARRIER_OPEN")
BARRIER_TIMEOUT_S = int(os.getenv("BARRIER_TIMEOUT_S", "30"))

WORK_SLEEP_SECONDS = float(os.getenv("WORK_SLEEP_SECONDS", "2"))

MAX_LOOPS = int(os.getenv("MAX_LOOPS", "0"))
EXIT_ON_SUCCESS = os.getenv("EXIT_ON_SUCCESS", "0") == "1"
EXIT_ON_STALE = os.getenv("EXIT_ON_STALE", "0") == "1"

METRICS_ENABLED = os.getenv("METRICS_ENABLED", "1") == "1"
METRICS_PORT = int(os.getenv("METRICS_PORT", "8000"))

# Test override: restrict claiming to one specific job id, but still obey lease rules.
CLAIM_JOB_ID = os.getenv("CLAIM_JOB_ID")


# ============================================================
# Clock
# ============================================================

class Clock:
    def now(self):
        return datetime.utcnow()


class SkewedClock(Clock):
    def __init__(self, offset_ms):
        self.offset = timedelta(milliseconds=offset_ms)

    def now(self):
        return datetime.utcnow() + self.offset


clock = SkewedClock(CLOCK_SKEW_MS) if CLOCK_SKEW_MS else Clock()


# ============================================================
# Logging
# ============================================================

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


# ============================================================
# Barriers
# ============================================================

def open_barrier(conn, cur, name):
    cur.execute(
        "INSERT INTO barriers(name) VALUES (%s) ON CONFLICT DO NOTHING",
        (name,),
    )
    # Ensure visibility across processes
    conn.commit()


def wait_barrier(cur, name, timeout_s):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        cur.execute("SELECT 1 FROM barriers WHERE name=%s", (name,))
        if cur.fetchone():
            return True
        time.sleep(0.2)
    return False


def maybe_barrier(conn, cur, point):
    if BARRIER_OPEN == point:
        log_event("barrier_open", name=point)
        open_barrier(conn, cur, point)

    if BARRIER_WAIT == point:
        log_event("barrier_wait", name=point)
        ok = wait_barrier(cur, point, BARRIER_TIMEOUT_S)
        if not ok:
            raise RuntimeError(f"barrier_timeout {point}")


# ============================================================
# Metrics
# ============================================================

heartbeat = Counter("faultline_worker_heartbeat_total", "Worker heartbeat ticks")
jobs_claimed = Counter("faultline_jobs_claimed_total", "Jobs claimed")
jobs_succeeded = Counter("faultline_jobs_succeeded_total", "Jobs succeeded")
jobs_failed = Counter("faultline_jobs_failed_total", "Jobs failed")
retries_total = Counter("faultline_retries_total", "Retries")


# ============================================================
# DB Helpers
# ============================================================

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
    raise RuntimeError("schema not ready")


# ============================================================
# Lease Claim
# ============================================================

def claim_one_job(conn, cur):
    lease_until = clock.now() + timedelta(seconds=LEASE_SECONDS)

    # Test override: claim a specific job, BUT still obey correctness rules:
    # - can claim if queued
    # - can reclaim if running and lease expired
    if CLAIM_JOB_ID:
        cur.execute(
            """
            UPDATE jobs
            SET state='running',
                lease_owner=%s,
                lease_expires_at=%s,
                fencing_token=fencing_token+1,
                updated_at=NOW()
            WHERE id=%s
              AND (
                    state='queued'
                 OR (state='running' AND lease_expires_at < NOW())
              )
            RETURNING id, fencing_token
            """,
            (WORKER_ID, lease_until, CLAIM_JOB_ID),
        )
        row = cur.fetchone()
        if row:
            job_id, token = row[0], int(row[1])
            log_event("lease_acquired", job_id=job_id, token=token, forced=True)

            maybe_barrier(conn, cur, "after_lease_acquire")
            maybe_crash("after_lease_acquire")

            return job_id, token

        return None, None

    # Normal (production) claim path
    cur.execute(
        """
        UPDATE jobs
        SET state='running',
            lease_owner=%s,
            lease_expires_at=%s,
            fencing_token=fencing_token+1,
            updated_at=NOW()
        WHERE id = (
            SELECT id
            FROM jobs
            WHERE (
                    state='queued'
                AND (next_run_at IS NULL OR next_run_at <= NOW())
            )
            OR (state='running' AND lease_expires_at < NOW())
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

        maybe_barrier(conn, cur, "after_lease_acquire")
        maybe_crash("after_lease_acquire")

        return job_id, token

    return None, None


# ============================================================
# Fence Enforcement (SQL-only lease check)
# ============================================================

def assert_fence(cur, job_id, token):
    cur.execute(
        """
        SELECT fencing_token,
               (lease_expires_at IS NOT NULL AND lease_expires_at < NOW())
        FROM jobs
        WHERE id=%s
        """,
        (job_id,),
    )

    row = cur.fetchone()
    if not row:
        raise RuntimeError("job_missing")

    current_token = int(row[0])
    lease_expired = bool(row[1])

    if token != current_token:
        log_event(
            "stale_write_blocked",
            job_id=job_id,
            stale_token=token,
            current_token=current_token,
            reason="token_mismatch",
        )
        raise RuntimeError("stale_token")

    if lease_expired:
        log_event(
            "stale_write_blocked",
            job_id=job_id,
            stale_token=token,
            current_token=current_token,
            reason="lease_expired",
        )
        raise RuntimeError("lease_expired")


# ============================================================
# Apply Path
# ============================================================

def mark_succeeded(cur, job_id, token):
    cur.execute(
        "SELECT fencing_token FROM jobs WHERE id=%s FOR UPDATE",
        (job_id,),
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError("job_missing")

    current_token = int(row[0])
    if token != current_token:
        log_event(
            "stale_write_blocked",
            job_id=job_id,
            stale_token=token,
            current_token=current_token,
            reason="token_mismatch_precommit",
        )
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


# ============================================================
# Main Loop
# ============================================================

if __name__ == "__main__":
    if METRICS_ENABLED:
        start_http_server(METRICS_PORT)

    wait_for_schema()

    loops = 0

    while True:
        if MAX_LOOPS and loops >= MAX_LOOPS:
            log_event("worker_exit", reason="max_loops")
            break

        loops += 1
        heartbeat.inc()

        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    job_id, token = claim_one_job(conn, cur)

                    if not job_id:
                        time.sleep(0.2)
                        continue

                    jobs_claimed.inc()
                    log_event("execution_started", job_id=job_id, token=token)

                    try:
                        assert_fence(cur, job_id, token)

                        maybe_crash("mid_execute")
                        time.sleep(WORK_SLEEP_SECONDS)

                        assert_fence(cur, job_id, token)

                        mark_succeeded(cur, job_id, token)
                        jobs_succeeded.inc()

                        if EXIT_ON_SUCCESS:
                            log_event("worker_exit", reason="success")
                            break

                    except Exception as e:
                        if str(e) in ("stale_token", "lease_expired") and EXIT_ON_STALE:
                            log_event("worker_exit", reason="stale")
                            break
                        raise

        except OperationalError:
            time.sleep(0.5)

        time.sleep(0.2)
from services.worker.transport_db import connect_db
from services.common.tracing import init_tracing, get_tracer, start_job_span_from_payload, start_span
import os
from prometheus_client import start_http_server
import time
import uuid
import json
from datetime import datetime, timezone

import psycopg2
from psycopg2 import OperationalError
from prometheus_client import Counter, Histogram, start_http_server

from services.worker.retry import backoff_seconds, mark_for_retry


# ============================================================
# Environment
# ============================================================

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_DSN")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL or POSTGRES_DSN must be set")
DATABASE_URL = DATABASE_URL.replace("postgresql+psycopg2://", "postgresql://", 1)
start_http_server(int(os.getenv("FAULTLINE_METRICS_PORT", "9108")))
WORKER_ID = str(uuid.uuid4())
init_tracing("faultline-worker")
tracer = get_tracer("faultline.worker")

LEASE_SECONDS = int(os.getenv("LEASE_SECONDS", "30"))
CRASH_AT = os.getenv("CRASH_AT")

BARRIER_WAIT = os.getenv("BARRIER_WAIT")
BARRIER_OPEN = os.getenv("BARRIER_OPEN")
BARRIER_TIMEOUT_S = int(os.getenv("BARRIER_TIMEOUT_S", "30"))

WORK_SLEEP_SECONDS = float(os.getenv("WORK_SLEEP_SECONDS", "2"))

MAX_LOOPS = int(os.getenv("MAX_LOOPS", "0"))
EXIT_ON_SUCCESS = os.getenv("EXIT_ON_SUCCESS", "0") == "1"
EXIT_ON_STALE = os.getenv("EXIT_ON_STALE", "0") == "1"

METRICS_ENABLED = os.getenv("METRICS_ENABLED", "1") == "1"
METRICS_PORT = int(os.getenv("METRICS_PORT", "8000"))

CLAIM_JOB_ID = os.getenv("CLAIM_JOB_ID")
AUTOPSY_LOG_PATH = os.getenv("AUTOPSY_LOG_PATH")
SIMULATE_FAILURE = os.getenv("SIMULATE_FAILURE", "0") == "1"


# ============================================================
# Logging
# ============================================================

def log_event(event, **fields):
    payload = {
        "event": event,
        "worker_id": WORKER_ID,
        "ts": datetime.now(timezone.utc).isoformat(),
        **fields,
    }
    line = json.dumps(payload)
    print(line, flush=True)
    if AUTOPSY_LOG_PATH:
        with open(AUTOPSY_LOG_PATH, "a") as f:
            f.write(line + "\n")


def maybe_crash(point):
    if CRASH_AT == point:
        log_event("crash_injected", point=point)
        os._exit(137)


# ============================================================
# Barrier helpers
# ============================================================

def open_barrier(conn, cur, name):
    cur.execute(
        "INSERT INTO barriers(name) VALUES (%s) ON CONFLICT DO NOTHING",
        (name,),
    )
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
jobs_failed_perm = Counter("faultline_jobs_failed_total", "Jobs permanently failed")
jobs_retried = Counter("faultline_jobs_retried_total", "Jobs scheduled for retry")
stale_commits = Counter("faultline_stale_commit_prevented_total", "Stale commits blocked")
job_duration = Histogram(
    "faultline_job_duration_seconds",
    "Job execution duration",
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60],
)


# ============================================================
# DB helpers
# ============================================================

def get_conn():
    return connect_db(DATABASE_URL)


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
# Lease claim
# Atomic UPDATE ... RETURNING fencing_token.
# FOR UPDATE SKIP LOCKED: concurrent workers never block each other.
# ============================================================

def claim_one_job(conn, cur):

    if CLAIM_JOB_ID:
        cur.execute(
            """
            UPDATE jobs
            SET state='running',
                lease_owner=%s,
                lease_expires_at = NOW() + make_interval(secs => %s),
                fencing_token=fencing_token+1,
                updated_at=NOW()
            WHERE id=%s
              AND (
                    state='queued'
                 OR (state='running' AND lease_expires_at < NOW())
              )
            RETURNING id, fencing_token, lease_expires_at, attempts, max_attempts
            """,
            (WORKER_ID, LEASE_SECONDS, CLAIM_JOB_ID),
        )
        row = cur.fetchone()
        if row:
            job_id, token, lease_expires_at, attempts, max_attempts = row
            with start_job_span_from_payload(
            tracer,
            "worker.claim",
            payload,
            job_id=str(job_id),
            worker_id=WORKER_ID,
            fencing_token=int(token),
        ):
            pass

        with start_job_span_from_payload(
            tracer,
            "lease.acquire",
            payload,
            job_id=str(job_id),
            lease_ttl=int(LEASE_SECONDS),
        ):
            pass

        log_event("lease_acquired", job_id=job_id, token=int(token),
                      lease_expires_at=str(lease_expires_at), forced=True,
                      attempts=attempts, max_attempts=max_attempts)
            maybe_barrier(conn, cur, "after_lease_acquire")
            maybe_crash("after_lease_acquire")
            return job_id, int(token), int(attempts), int(max_attempts)
        return None, None, None, None

    cur.execute(
        """
        UPDATE jobs
        SET state='running',
            lease_owner=%s,
            lease_expires_at = NOW() + make_interval(secs => %s),
            fencing_token=fencing_token+1,
            updated_at=NOW()
        WHERE id = (
            SELECT id FROM jobs
            WHERE (state='queued' AND (next_run_at IS NULL OR next_run_at <= NOW()))
               OR (state='running' AND lease_expires_at < NOW())
            ORDER BY COALESCE(next_run_at, created_at)
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        RETURNING id, fencing_token, lease_expires_at, attempts, max_attempts
        """,
        (WORKER_ID, LEASE_SECONDS),
    )
    row = cur.fetchone()
    if row:
        job_id, token, lease_expires_at, attempts, max_attempts = row
        log_event("lease_acquired", job_id=job_id, token=int(token),
                  lease_expires_at=str(lease_expires_at),
                  attempts=attempts, max_attempts=max_attempts)
        maybe_barrier(conn, cur, "after_lease_acquire")
        maybe_crash("after_lease_acquire")
        return job_id, int(token), int(attempts), int(max_attempts)

    return None, None, None, None


# ============================================================
# Fence enforcement
# ============================================================

def assert_fence(cur, job_id, token):
    cur.execute(
        """
        SELECT fencing_token,
               (lease_expires_at IS NOT NULL AND lease_expires_at < NOW())
        FROM jobs WHERE id=%s
        """,
        (job_id,),
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError("job_missing")

    current_token = int(row[0])
    lease_expired = bool(row[1])

    if token != current_token:
        log_event("stale_write_blocked", job_id=job_id, stale_token=token,
                  current_token=current_token, reason="token_mismatch")
        stale_commits.inc()
        raise RuntimeError("stale_token")

    if lease_expired:
        log_event("stale_write_blocked", job_id=job_id, stale_token=token,
                  current_token=current_token, reason="lease_expired")
        stale_commits.inc()
        raise RuntimeError("lease_expired")


# ============================================================
# Guarded commit
# ============================================================

def mark_succeeded(cur, job_id, token):
    cur.execute(
        """
        INSERT INTO ledger_entries (job_id, fencing_token, account_id, delta)
        VALUES (%s, %s, 'default', 1)
        ON CONFLICT (job_id, fencing_token) DO NOTHING
        """,
        (job_id, token),
    )

    maybe_crash("before_commit")

    cur.execute(
        """
        UPDATE jobs
        SET state='succeeded',
            lease_owner=NULL,
            lease_expires_at=NULL,
            next_run_at=NULL,
            updated_at=NOW()
        WHERE id=%s
          AND state='running'
          AND lease_owner=%s
          AND fencing_token=%s
          AND EXISTS (
              SELECT 1 FROM ledger_entries
              WHERE job_id=%s AND fencing_token=%s
          )
        """,
        (job_id, WORKER_ID, token, job_id, token),
    )

    if cur.rowcount == 0:
        log_event("commit_stale", job_id=job_id, token=token)
        with start_job_span_from_payload(
            tracer,
            "lease.expire",
            payload,
            job_id=str(job_id),
            reason="stale",
        ):
            pass

        stale_commits.inc()
        raise RuntimeError("stale_commit")


# ============================================================
# Job execution
# ============================================================

def execute_job(job_id, token, attempts):
    if SIMULATE_FAILURE and attempts == 0:
        raise RuntimeError("simulated_execution_failure")
    time.sleep(WORK_SLEEP_SECONDS)


# ============================================================
# Main loop
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
                    job_id, token, attempts, max_attempts = claim_one_job(conn, cur)

                    if not job_id:
                        time.sleep(0.2)
                        continue

                    conn.commit()
                    jobs_claimed.inc()

                    log_event("execution_started", job_id=job_id, token=token,
                              attempts=attempts, max_attempts=max_attempts)

                    start = time.monotonic()

                    try:
                        assert_fence(cur, job_id, token)

                        try:
                            with start_job_span_from_payload(
                tracer,
                "job.execute",
                payload,
                job_id=str(job_id),
            ):
                execute_job(job_id, token, attempts)
                        except Exception as exec_err:
                            outcome = mark_for_retry(
                                cur, job_id, token, attempts,
                                max_attempts, str(exec_err)
                            )
                            elapsed = time.monotonic() - start
                            job_duration.observe(elapsed)
                            if outcome == "failed":
                                jobs_failed_perm.inc()
                                log_event("job_failed_permanently", job_id=job_id,
                                          attempts=attempts + 1)
                            else:
                                jobs_retried.inc()
                                log_event("job_scheduled_retry", job_id=job_id,
                                          attempt=attempts + 1,
                                          backoff_seconds=backoff_seconds(attempts + 1))
                            conn.commit()
                            continue

                        assert_fence(cur, job_id, token)
                        mark_succeeded(cur, job_id, token)
                        elapsed = time.monotonic() - start
                        job_duration.observe(elapsed)
                        jobs_succeeded.inc()

                        log_event("commit_ok", job_id=job_id, token=token,
                                  duration_s=round(elapsed, 3))

                        if EXIT_ON_SUCCESS:
                            log_event("worker_exit", reason="success")
                            break

                    except Exception as e:
                        if str(e) in ("stale_token", "lease_expired", "stale_commit"):
                            if EXIT_ON_STALE:
                                log_event("worker_exit", reason="stale")
                                break
                        raise

        except OperationalError as e:
            log_event("db_error", error=str(e)[:200])
            time.sleep(0.5)

        time.sleep(0.2)
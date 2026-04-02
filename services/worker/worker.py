import json
import os
import time
import uuid

import psycopg2
from psycopg2 import OperationalError
from prometheus_client import Counter, Histogram, start_http_server

from common.observability.tracing import get_tracer
from services.worker.autopsy import log_event
from services.worker.spans import start_job_span_from_payload, start_span
from services.worker.transport_db import get_conn

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_DSN")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL or POSTGRES_DSN must be set")

WORKER_ID = os.getenv("FAULTLINE_WORKER_ID") or os.getenv("WORKER_ID") or str(uuid.uuid4())
LEASE_SECONDS = int(os.getenv("LEASE_SECONDS", "30"))
WORK_SLEEP_SECONDS = float(os.getenv("WORK_SLEEP_SECONDS", "2"))
MAX_LOOPS = int(os.getenv("MAX_LOOPS", "0"))
SIMULATE_FAILURE = os.getenv("SIMULATE_FAILURE", "0") == "1"
CLAIM_JOB_ID = os.getenv("CLAIM_JOB_ID")
EXIT_ON_SUCCESS = os.getenv("EXIT_ON_SUCCESS", "0") == "1"
EXIT_ON_STALE = os.getenv("EXIT_ON_STALE", "0") == "1"
METRICS_ENABLED = os.getenv("METRICS_ENABLED", "1") != "0"
METRICS_PORT = int(os.getenv("FAULTLINE_METRICS_PORT", "9108"))
OTEL_TRACE_LOG = os.getenv("FAULTLINE_OTEL_TRACE_LOG", "docs/autopsy/assets/otel_trace_chain.jsonl")

tracer = get_tracer("faultline.worker")

heartbeat = Counter("faultline_worker_heartbeat_total", "Worker loop heartbeats")
jobs_claimed = Counter("faultline_jobs_claimed_total", "Jobs claimed")
jobs_succeeded = Counter("faultline_jobs_succeeded_total", "Jobs succeeded")
jobs_retried = Counter("faultline_jobs_retried_total", "Jobs retried")
jobs_failed_perm = Counter("faultline_jobs_failed_perm_total", "Jobs permanently failed")
stale_commits = Counter("faultline_stale_commits_blocked_total", "Stale commits blocked")
job_duration = Histogram("faultline_job_duration_seconds", "Job execution duration")



def _append_trace_event(event: str, **fields) -> None:
    path = OTEL_TRACE_LOG
    if not path:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {"ts": round(time.time(), 6), "event": event, **fields}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, sort_keys=True) + "\n")


def wait_for_schema(timeout_s: float = 30.0):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM jobs LIMIT 1;")
                    return
        except Exception:
            time.sleep(2)
    raise RuntimeError("schema not ready")


def maybe_crash(phase: str):
    if os.getenv("CRASH_PHASE") == phase:
        raise RuntimeError(f"simulated_crash:{phase}")


def maybe_barrier(conn, cur, name: str):
    barrier_open = os.getenv("BARRIER_OPEN")
    barrier_wait = os.getenv("BARRIER_WAIT")
    barrier_timeout_s = float(os.getenv("BARRIER_TIMEOUT_S", "60"))

    if barrier_open == name:
        cur.execute(
            """
            INSERT INTO barriers(name, opened_at)
            VALUES (%s, NOW())
            ON CONFLICT (name) DO UPDATE SET opened_at = EXCLUDED.opened_at
            """,
            (name,),
        )
        conn.commit()
        log_event("barrier_open", barrier=name)
        _append_trace_event("barrier_open", barrier=name, worker_id=WORKER_ID)

    if barrier_wait == name:
        deadline = time.time() + barrier_timeout_s
        while time.time() < deadline:
            cur.execute("SELECT 1 FROM barriers WHERE name=%s", (name,))
            if cur.fetchone():
                log_event("barrier_seen", barrier=name)
                _append_trace_event("barrier_seen", barrier=name, worker_id=WORKER_ID)
                return
            time.sleep(0.05)
        raise RuntimeError(f"barrier_timeout:{name}")


def backoff_seconds(attempt: int) -> int:
    return min(2 * (2 ** max(0, attempt - 1)), 300)


def claim_one_job(conn, cur):
    barrier_wait = os.getenv("BARRIER_WAIT")
    if barrier_wait:
        cur.execute("SELECT opened_at FROM barriers WHERE name=%s", (barrier_wait,))
        if cur.fetchone() is None:
            return None, None, None, None, None

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
            RETURNING id, payload, fencing_token, lease_expires_at, attempts, max_attempts
            """,
            (WORKER_ID, LEASE_SECONDS, CLAIM_JOB_ID),
        )
        row = cur.fetchone()
        if row:
            job_id, payload, token, lease_expires_at, attempts, max_attempts = row
            with start_job_span_from_payload(
                tracer,
                "worker.claim",
                payload,
                job_id=str(job_id),
                worker_id=WORKER_ID,
                fencing_token=int(token),
            ):
                _append_trace_event(
                    "claim",
                    job_id=str(job_id),
                    worker_id=WORKER_ID,
                    fencing_token=int(token),
                    forced=True,
                )
            with start_job_span_from_payload(
                tracer,
                "lease.acquire",
                payload,
                job_id=str(job_id),
                lease_ttl=int(LEASE_SECONDS),
            ):
                pass
            log_event(
                "lease_acquired",
                job_id=job_id,
                token=int(token),
                lease_expires_at=str(lease_expires_at),
                forced=True,
                attempts=attempts,
                max_attempts=max_attempts,
            )
            maybe_barrier(conn, cur, "after_lease_acquire")
            maybe_crash("after_lease_acquire")
            return job_id, payload, int(token), int(attempts), int(max_attempts)
        cur.execute(
            "SELECT state, lease_owner, lease_expires_at, fencing_token FROM jobs WHERE id=%s",
            (CLAIM_JOB_ID,),
        )
        print("JOB STATE BEFORE CLAIM:", cur.fetchone(), flush=True)
        return None, None, None, None, None

    cur.execute(
        """
        UPDATE jobs
        SET state='running',
            lease_owner=%s,
            lease_expires_at = NOW() + make_interval(secs => %s),
            fencing_token=fencing_token+1,
            updated_at=NOW()
        WHERE id = (
            SELECT id
            FROM jobs
            WHERE (state='queued' AND (next_run_at IS NULL OR next_run_at <= NOW()))
               OR (state='running' AND lease_expires_at < NOW())
            ORDER BY COALESCE(next_run_at, created_at)
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        RETURNING id, payload, fencing_token, lease_expires_at, attempts, max_attempts
        """,
        (WORKER_ID, LEASE_SECONDS),
    )
    row = cur.fetchone()
    if row:
        job_id, payload, token, lease_expires_at, attempts, max_attempts = row
        with start_job_span_from_payload(
            tracer,
            "worker.claim",
            payload,
            job_id=str(job_id),
            worker_id=WORKER_ID,
            fencing_token=int(token),
        ):
            _append_trace_event(
                "claim",
                job_id=str(job_id),
                worker_id=WORKER_ID,
                fencing_token=int(token),
                forced=False,
            )
        with start_job_span_from_payload(
            tracer, "lease.acquire", payload, job_id=str(job_id), lease_ttl=int(LEASE_SECONDS)
        ):
            pass
        log_event(
            "lease_acquired",
            job_id=job_id,
            token=int(token),
            lease_expires_at=str(lease_expires_at),
            attempts=attempts,
            max_attempts=max_attempts,
        )
        maybe_barrier(conn, cur, "after_lease_acquire")
        maybe_crash("after_lease_acquire")
        return job_id, payload, int(token), int(attempts), int(max_attempts)

    return None, None, None, None, None


def assert_fence(cur, job_id, token):
    cur.execute(
        """
        SELECT fencing_token, (lease_expires_at IS NOT NULL AND lease_expires_at < NOW())
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
        _append_trace_event(
            "stale_write_blocked",
            job_id=str(job_id),
            stale_token=int(token),
            current_token=current_token,
            reason="token_mismatch",
        )
        stale_commits.inc()
        raise RuntimeError("stale_token")

    if lease_expired:
        log_event(
            "stale_write_blocked",
            job_id=job_id,
            stale_token=token,
            current_token=current_token,
            reason="lease_expired",
        )
        _append_trace_event(
            "stale_write_blocked",
            job_id=str(job_id),
            stale_token=int(token),
            current_token=current_token,
            reason="lease_expired",
        )
        stale_commits.inc()
        raise RuntimeError("lease_expired")


def execute_job(job_id, token, attempts):
    if SIMULATE_FAILURE and attempts == 0:
        raise RuntimeError("simulated_execution_failure")
    _append_trace_event("execute_start", job_id=str(job_id), token=int(token), attempts=int(attempts))
    time.sleep(WORK_SLEEP_SECONDS)
    _append_trace_event("execute_done", job_id=str(job_id), token=int(token), attempts=int(attempts))


def mark_for_retry(cur, job_id, token, attempts, max_attempts, error_text):
    next_attempt = attempts + 1
    if next_attempt >= max_attempts:
        cur.execute(
            """
            UPDATE jobs
            SET state='failed',
                attempts=%s,
                last_error=%s,
                lease_owner=NULL,
                lease_expires_at=NULL,
                updated_at=NOW()
            WHERE id=%s AND fencing_token=%s
            """,
            (next_attempt, error_text[:500], job_id, token),
        )
        return "failed"

    delay = backoff_seconds(next_attempt)
    cur.execute(
        """
        UPDATE jobs
        SET state='queued',
            attempts=%s,
            last_error=%s,
            lease_owner=NULL,
            lease_expires_at=NULL,
            next_run_at=NOW() + make_interval(secs => %s),
            updated_at=NOW()
        WHERE id=%s AND fencing_token=%s
        """,
        (next_attempt, error_text[:500], delay, job_id, token),
    )
    return "retry"


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
                SELECT 1
                FROM ledger_entries
                WHERE job_id=%s AND fencing_token=%s
          )
        """,
        (job_id, WORKER_ID, token, job_id, token),
    )
    if cur.rowcount == 0:
        log_event("commit_stale", job_id=job_id, token=token)
        stale_commits.inc()
        raise RuntimeError("stale_commit")


if __name__ == "__main__":
    if METRICS_ENABLED:
        start_http_server(METRICS_PORT)

    wait_for_schema()
    loops = 0
    run_once = os.getenv("FAULTLINE_SINGLE_RUN", "0") == "1"

    while True:
        if MAX_LOOPS and loops >= MAX_LOOPS:
            log_event("worker_exit", reason="max_loops")
            break

        loops += 1
        heartbeat.inc()

        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    result = claim_one_job(conn, cur)
                    if not result or result[0] is None:
                        if CLAIM_JOB_ID and run_once:
                            log_event("worker_exit", reason="forced_claim_failed")
                            break
                        time.sleep(0.05)
                        continue

                    job_id, payload, token, attempts, max_attempts = result
                    conn.commit()
                    jobs_claimed.inc()
                    log_event(
                        "execution_started",
                        job_id=job_id,
                        token=token,
                        attempts=attempts,
                        max_attempts=max_attempts,
                    )

                    start = time.monotonic()
                    try:
                        assert_fence(cur, job_id, token)
                        try:
                            with start_job_span_from_payload(tracer, "job.execute", payload, job_id=str(job_id)):
                                execute_job(job_id, token, attempts)
                        except Exception as exec_err:
                            outcome = mark_for_retry(cur, job_id, token, attempts, max_attempts, str(exec_err))
                            elapsed = time.monotonic() - start
                            job_duration.observe(elapsed)
                            if outcome == "failed":
                                jobs_failed_perm.inc()
                                log_event("job_failed_permanently", job_id=job_id, attempts=attempts + 1)
                            else:
                                jobs_retried.inc()
                                log_event(
                                    "job_scheduled_retry",
                                    job_id=job_id,
                                    attempt=attempts + 1,
                                    backoff_seconds=backoff_seconds(attempts + 1),
                                )
                            conn.commit()
                            if run_once:
                                log_event("worker_exit", reason="single_run_retry")
                                break
                            continue

                        assert_fence(cur, job_id, token)
                        mark_succeeded(cur, job_id, token)
                        elapsed = time.monotonic() - start
                        job_duration.observe(elapsed)
                        jobs_succeeded.inc()
                        with start_job_span_from_payload(
                            tracer,
                            "job.complete",
                            payload,
                            job_id=str(job_id),
                            status="succeeded",
                        ):
                            _append_trace_event(
                                "complete",
                                job_id=str(job_id),
                                worker_id=WORKER_ID,
                                token=int(token),
                                duration_s=round(elapsed, 3),
                            )
                        log_event("commit_ok", job_id=job_id, token=token, duration_s=round(elapsed, 3))
                        conn.commit()
                        if EXIT_ON_SUCCESS:
                            log_event("worker_exit", reason="success")
                            break
                        if run_once:
                            log_event("worker_exit", reason="single_run")
                            break
                    except Exception as e:
                        conn.rollback()
                        if str(e) in ("stale_token", "lease_expired", "stale_commit"):
                            if EXIT_ON_STALE:
                                log_event("worker_exit", reason="stale")
                                break
                        raise
        except OperationalError as e:
            log_event("db_error", error=str(e)[:200])
            time.sleep(0.5)

        time.sleep(0.2)

import hashlib
import json
import os
import random
import subprocess
import sys
import time
import uuid
from pathlib import Path

import psycopg2

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "benchmarks" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://faultline:faultline@localhost:5432/faultline")
JOB_COUNT = int(os.environ.get("NAIVE_JOB_COUNT", "200"))
WORKER_COUNT = int(os.environ.get("NAIVE_WORKER_COUNT", "8"))
FAULT_PCT = int(os.environ.get("NAIVE_FAULT_PCT", "5"))
SEED = int(os.environ.get("NAIVE_SEED", "7"))
LEASE_SECONDS = int(os.environ.get("NAIVE_LEASE_SECONDS", "2"))
POLL_SLEEP = float(os.environ.get("NAIVE_POLL_SLEEP", "0.02"))
MAX_RUNTIME_SECONDS = int(os.environ.get("NAIVE_MAX_RUNTIME_SECONDS", "90"))

random.seed(SEED)


def db():
    return psycopg2.connect(DATABASE_URL)


def ensure_naive_table():
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS naive_benchmark_commits (
                    commit_id BIGSERIAL PRIMARY KEY,
                    job_id UUID NOT NULL,
                    worker_id TEXT NOT NULL,
                    committed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        conn.commit()


def reset_tables():
    ensure_naive_table()
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM naive_benchmark_commits")
            cur.execute("DELETE FROM ledger_entries")
            cur.execute("DELETE FROM jobs")
        conn.commit()


def seed_jobs(count: int):
    h = hashlib.sha256(b"{}").hexdigest()
    job_ids = [str(uuid.uuid4()) for _ in range(count)]
    with db() as conn:
        with conn.cursor() as cur:
            for jid in job_ids:
                cur.execute(
                    """
                    INSERT INTO jobs (id, payload, payload_hash, state, attempts, max_attempts, next_run_at, fencing_token)
                    VALUES (%s, '{}'::jsonb, %s, 'queued', 0, 3, NOW(), 0)
                    """,
                    (jid, h),
                )
        conn.commit()
    return job_ids


def count_duplicates(job_ids):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE cnt > 1) AS duplicate_jobs,
                    COALESCE(SUM(cnt - 1) FILTER (WHERE cnt > 1), 0) AS duplicate_entries,
                    COUNT(*) FILTER (WHERE cnt = 0) AS missing_jobs
                FROM (
                    SELECT j.id, COUNT(n.commit_id) AS cnt
                    FROM jobs j
                    LEFT JOIN naive_benchmark_commits n ON n.job_id = j.id
                    WHERE j.id = ANY(%s::uuid[])
                    GROUP BY j.id
                ) t
                """,
                (job_ids,),
            )
            return cur.fetchone()


def count_states(job_ids):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT state, COUNT(*) FROM jobs WHERE id = ANY(%s::uuid[]) GROUP BY state",
                (job_ids,),
            )
            return dict(cur.fetchall())


NAIVE_WORKER = r'''
import os
import random
import time
import uuid
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]
WORKER_ID = os.environ.get("NAIVE_WORKER_ID", str(uuid.uuid4()))
FAULT_PCT = int(os.environ.get("NAIVE_FAULT_PCT", "5"))
LEASE_SECONDS = int(os.environ.get("NAIVE_LEASE_SECONDS", "2"))
POLL_SLEEP = float(os.environ.get("NAIVE_POLL_SLEEP", "0.02"))
MAX_RUNTIME_SECONDS = int(os.environ.get("NAIVE_MAX_RUNTIME_SECONDS", "90"))
SEED = int(os.environ.get("NAIVE_SEED", "7"))
random.seed(SEED + abs(hash(WORKER_ID)) % 100000)

deadline = time.time() + MAX_RUNTIME_SECONDS

def connect():
    return psycopg2.connect(DATABASE_URL)

while time.time() < deadline:
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    WITH candidate AS (
                        SELECT id
                        FROM jobs
                        WHERE state = 'queued'
                           OR (state = 'running' AND lease_expires_at IS NOT NULL AND lease_expires_at < NOW())
                        ORDER BY updated_at NULLS FIRST, created_at NULLS FIRST
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED
                    )
                    UPDATE jobs
                    SET state='running',
                        lease_owner=%s,
                        lease_expires_at=NOW() + make_interval(secs => %s),
                        updated_at=NOW()
                    WHERE id IN (SELECT id FROM candidate)
                    RETURNING id
                    """,
                    (WORKER_ID, LEASE_SECONDS),
                )
                row = cur.fetchone()
                if not row:
                    conn.commit()
                    time.sleep(POLL_SLEEP)
                    continue

                job_id = str(row[0])
                conn.commit()

        time.sleep(random.uniform(0.01, 0.12))

        inject_fault = random.random() < (FAULT_PCT / 100.0)
        if inject_fault:
            time.sleep(LEASE_SECONDS + random.uniform(0.05, 0.25))

        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO naive_benchmark_commits (job_id, worker_id)
                    VALUES (%s, %s)
                    """,
                    (job_id, WORKER_ID),
                )
                cur.execute(
                    """
                    UPDATE jobs
                    SET state='succeeded',
                        lease_owner=NULL,
                        lease_expires_at=NULL,
                        updated_at=NOW()
                    WHERE id=%s
                    """,
                    (job_id,),
                )
            conn.commit()

    except Exception as e:
        print(f"[{WORKER_ID}] job_id={locals().get('job_id')} error={type(e).__name__}: {e}", flush=True)
        time.sleep(POLL_SLEEP)
'''

def run_worker_processes():
    workers = []
    for i in range(WORKER_COUNT):
        env = os.environ.copy()
        env["DATABASE_URL"] = DATABASE_URL
        env["NAIVE_WORKER_ID"] = f"naive-worker-{i}"
        env["NAIVE_FAULT_PCT"] = str(FAULT_PCT)
        env["NAIVE_LEASE_SECONDS"] = str(LEASE_SECONDS)
        env["NAIVE_POLL_SLEEP"] = str(POLL_SLEEP)
        env["NAIVE_MAX_RUNTIME_SECONDS"] = str(MAX_RUNTIME_SECONDS)
        env["NAIVE_SEED"] = str(SEED + i)
        p = subprocess.Popen(
            [sys.executable, "-c", NAIVE_WORKER],
            env=env,
            stdout=None,
            stderr=None,
            text=True,
        )
        workers.append(p)
    return workers


def kill_all(workers):
    for p in workers:
        try:
            if p.poll() is None:
                p.kill()
            p.communicate(timeout=2)
        except Exception:
            pass


def wait_until_done(job_ids):
    deadline = time.time() + MAX_RUNTIME_SECONDS
    while time.time() < deadline:
        counts = count_states(job_ids)
        pending = counts.get("queued", 0) + counts.get("running", 0)
        if pending == 0:
            return True
        time.sleep(0.5)
    return False


def debug_single_insert():
    reset_tables()
    job_ids = seed_jobs(1)
    job_id = job_ids[0]
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE jobs
                SET state='running',
                    lease_owner='debug-worker',
                    lease_expires_at=NOW() + interval '2 seconds',
                    updated_at=NOW()
                WHERE id=%s
                RETURNING id
                """,
                (job_id,),
            )
            print("claimed:", cur.fetchone())
        conn.commit()

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO naive_benchmark_commits (job_id, worker_id)
                VALUES (%s, %s)
                RETURNING commit_id
                """,
                (job_id, 'debug-worker'),
            )
            print("naive commit insert ok:", cur.fetchone())
            cur.execute(
                """
                UPDATE jobs
                SET state='succeeded',
                    lease_owner=NULL,
                    lease_expires_at=NULL,
                    updated_at=NOW()
                WHERE id=%s
                RETURNING state
                """,
                (job_id,),
            )
            print("job update ok:", cur.fetchone())
        conn.commit()


def main():
    reset_tables()
    job_ids = seed_jobs(JOB_COUNT)
    workers = run_worker_processes()
    completed = wait_until_done(job_ids)
    kill_all(workers)

    duplicate_jobs, duplicate_entries, missing_jobs = count_duplicates(job_ids)
    counts = count_states(job_ids)
    succeeded = counts.get("succeeded", 0)
    failed = counts.get("failed", 0)
    queued = counts.get("queued", 0)
    running = counts.get("running", 0)

    duplicate_jobs = int(duplicate_jobs or 0)
    duplicate_entries = int(duplicate_entries or 0)
    missing_jobs = int(missing_jobs or 0)
    duplicate_commit_rate = round((duplicate_entries / JOB_COUNT) * 100.0, 4)

    result = {
        "system": "naive_queue",
        "job_count": JOB_COUNT,
        "worker_count": WORKER_COUNT,
        "fault_pct": FAULT_PCT,
        "completed": completed,
        "succeeded": succeeded,
        "failed": failed,
        "queued": queued,
        "running": running,
        "duplicate_jobs": duplicate_jobs,
        "duplicate_entries": duplicate_entries,
        "missing_jobs": missing_jobs,
        "duplicate_commit_rate_percent": duplicate_commit_rate,
    }

    out = RESULTS_DIR / f"naive_fault_{FAULT_PCT}.json"
    out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

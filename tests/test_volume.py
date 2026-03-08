"""
tests/test_volume.py
─────────────────────
Volume test: 1,000 jobs processed by multiple concurrent workers.

Validates:
  - All 1,000 jobs reach state=succeeded
  - Exactly 1 ledger entry per job (no duplicate executions)
  - No jobs permanently stuck
"""

import hashlib
import os
import subprocess
import sys
import time
import uuid

import psycopg2

# Ensure repo root is importable for worker subprocess
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKER_CMD = [sys.executable, "services/worker/worker.py"]
JOB_COUNT = 1000
WORKER_COUNT = 8
LEASE_SECONDS = 10          # short leases so in-flight jobs recover quickly after kill
RESULTS_PATH = "tests/results/volume_1000_jobs.txt"


def _db(url):
    return psycopg2.connect(url)


def _seed_jobs(database_url, count):
    h = hashlib.sha256(b"{}").hexdigest()
    job_ids = [str(uuid.uuid4()) for _ in range(count)]
    with _db(database_url) as conn:
        with conn.cursor() as cur:
            for jid in job_ids:
                cur.execute(
                    """
                    INSERT INTO jobs (id, payload, payload_hash, state, attempts,
                                     max_attempts, next_run_at)
                    VALUES (%s, '{}', %s, 'queued', 0, 3, NOW())
                    """,
                    (jid, h),
                )
        conn.commit()
    return job_ids


def _count_states(database_url, job_ids):
    with _db(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT state, COUNT(*) FROM jobs WHERE id = ANY(%s::uuid[]) GROUP BY state",
                (job_ids,),
            )
            return dict(cur.fetchall())


def _wait_drained(database_url, job_ids, timeout_s=240):
    """Wait until no jobs are in queued or running state."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        counts = _count_states(database_url, job_ids)
        pending = counts.get("queued", 0) + counts.get("running", 0)
        succeeded = counts.get("succeeded", 0)
        if pending == 0:
            return True
        if time.time() % 10 < 0.3:
            print(
                f"  progress: succeeded={succeeded} queued={counts.get('queued',0)} "
                f"running={counts.get('running',0)}",
                flush=True,
            )
        time.sleep(1)
    return False


def _kill(p):
    try:
        if p.poll() is None:
            p.kill()
        p.communicate(timeout=3)
    except Exception:
        pass


def _run_workers(database_url, count, extra_env=None):
    base_env = os.environ.copy()
    base_env.update({
        "DATABASE_URL": database_url,
        "METRICS_ENABLED": "0",
        "WORK_SLEEP_SECONDS": "0",
        "LEASE_SECONDS": str(LEASE_SECONDS),
        "MAX_LOOPS": "0",
        "PYTHONPATH": REPO_ROOT,
    })
    if extra_env:
        base_env.update(extra_env)

    workers = []
    for i in range(count):
        env = base_env.copy()
        env["METRICS_PORT"] = str(8100 + i)
        p = subprocess.Popen(
            WORKER_CMD, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        workers.append(p)
    return workers


def test_volume_1000_jobs_exactly_once(database_url):
    """
    Enqueue 1,000 jobs and process with 8 concurrent workers.
    Assert all reach succeeded with exactly 1 ledger entry each.
    """
    os.makedirs("tests/results", exist_ok=True)

    print(f"\n  Seeding {JOB_COUNT} jobs...", flush=True)
    job_ids = _seed_jobs(database_url, JOB_COUNT)

    print(f"  Starting {WORKER_COUNT} workers (LEASE_SECONDS={LEASE_SECONDS})...", flush=True)
    workers = _run_workers(database_url, WORKER_COUNT)

    drained = _wait_drained(database_url, job_ids, timeout_s=240)

    for p in workers:
        _kill(p)

    if not drained:
        # Leases are short (10s) — wait for any in-flight leases to expire
        # then run a second cleanup pass to finish any remaining jobs
        print(f"  First pass incomplete — waiting {LEASE_SECONDS + 2}s for leases to expire...",
              flush=True)
        time.sleep(LEASE_SECONDS + 2)

        print("  Starting cleanup worker pass...", flush=True)
        cleanup_workers = _run_workers(database_url, WORKER_COUNT)
        _wait_drained(database_url, job_ids, timeout_s=120)
        for p in cleanup_workers:
            _kill(p)

    # Final state counts
    counts = _count_states(database_url, job_ids)
    succeeded = counts.get("succeeded", 0)
    failed = counts.get("failed", 0)
    stuck = counts.get("running", 0) + counts.get("queued", 0)

    # Ledger entry analysis
    with _db(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE ledger_count = 1) AS exactly_one,
                    COUNT(*) FILTER (WHERE ledger_count > 1) AS duplicates,
                    COUNT(*) FILTER (WHERE ledger_count = 0) AS missing
                FROM (
                    SELECT j.id, COUNT(l.entry_id) AS ledger_count
                    FROM jobs j
                    LEFT JOIN ledger_entries l ON l.job_id = j.id
                    WHERE j.id = ANY(%s::uuid[])
                    GROUP BY j.id
                ) sub
                """,
                (job_ids,),
            )
            exactly_one, duplicates, missing = cur.fetchone()

    verdict = (
        f"{JOB_COUNT} jobs processed — 0 duplicate executions"
        if duplicates == 0 and succeeded == JOB_COUNT
        else "FAILURES DETECTED"
    )

    with open(RESULTS_PATH, "w") as f:
        f.write(f"Faultline Volume Test — {JOB_COUNT} jobs, {WORKER_COUNT} workers\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Jobs succeeded     : {succeeded}/{JOB_COUNT}\n")
        f.write(f"Jobs failed        : {failed}\n")
        f.write(f"Jobs stuck         : {stuck}\n")
        f.write(f"Ledger exactly-one : {exactly_one}/{JOB_COUNT}\n")
        f.write(f"Ledger duplicates  : {duplicates}\n")
        f.write(f"Ledger missing     : {missing}\n")
        f.write(f"\n{verdict}\n")

    print(f"\n  {verdict}", flush=True)

    assert duplicates == 0, f"{duplicates} duplicate ledger entries. See {RESULTS_PATH}"
    assert stuck == 0, f"{stuck} jobs stuck. See {RESULTS_PATH}"
    assert succeeded == JOB_COUNT, (
        f"Only {succeeded}/{JOB_COUNT} succeeded (failed={failed}). See {RESULTS_PATH}"
    )
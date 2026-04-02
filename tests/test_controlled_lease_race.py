import json
import os
import pathlib
import subprocess
import time
import uuid

import psycopg2
import pytest

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://faultline:faultline@localhost:5432/faultline")
ARTIFACT_DIR = pathlib.Path("artifacts/races")
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


def db():
    return psycopg2.connect(DATABASE_URL)


def wait_until(predicate, timeout=15, interval=0.1, label="condition"):
    start = time.time()
    while time.time() - start < timeout:
        if predicate():
            return True
        time.sleep(interval)
    raise AssertionError(f"Timed out waiting for {label}")


def seed_job(cur, job_id):
    cur.execute(
        """
        INSERT INTO jobs (id, payload, state, attempts, max_attempts, fencing_token, created_at, updated_at)
        VALUES (%s, %s::jsonb, 'queued', 0, 3, 0, NOW(), NOW())
        ON CONFLICT (id) DO UPDATE
        SET payload = EXCLUDED.payload,
            state='queued',
            attempts=0,
            max_attempts=3,
            fencing_token=0,
            lease_owner=NULL,
            lease_expires_at=NULL,
            completed_at=NULL,
            last_error=NULL,
            updated_at=NOW()
        """,
        (job_id, json.dumps({"kind": "lease_race_test"})),
    )


def fetch_job(job_id):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, state, lease_owner, fencing_token,
                       lease_expires_at, completed_at, attempts, last_error
                FROM jobs
                WHERE id=%s
                """,
                (job_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "state": row[1],
                "lease_owner": row[2],
                "fencing_token": row[3],
                "lease_expires_at": None if row[4] is None else row[4].isoformat(),
                "completed_at": None if row[5] is None else row[5].isoformat(),
                "attempts": row[6],
                "last_error": row[7],
            }


def worker_cmd(worker_id, job_id, hold_seconds):
    env = os.environ.copy()
    env["FAULTLINE_WORKER_ID"] = worker_id
    env["CLAIM_JOB_ID"] = job_id
    env["RACE_HOLD_SECONDS"] = str(hold_seconds)
    env["PYTHONUNBUFFERED"] = "1"
    return ["python3", "-m", "services.worker.worker"], env


def write_artifact(job_id, worker_a_log, worker_b_log, final_state):
    path = ARTIFACT_DIR / f"{job_id}.json"
    path.write_text(
        json.dumps(
            {
                "job_id": job_id,
                "worker_a_log": worker_a_log,
                "worker_b_log": worker_b_log,
                "final_state": final_state,
            },
            indent=2,
        )
    )
    return path


@pytest.mark.timeout(60)
def test_controlled_lease_race_stale_commit_rejected():
    job_id = f"lease-race-{uuid.uuid4().hex[:12]}"

    with db() as conn:
        with conn.cursor() as cur:
            seed_job(cur, job_id)
        conn.commit()

    a_cmd, a_env = worker_cmd("worker-a", job_id, hold_seconds=8)
    b_cmd, b_env = worker_cmd("worker-b", job_id, hold_seconds=0)

    worker_a = subprocess.Popen(a_cmd, env=a_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    def worker_a_owns_first():
        state = fetch_job(job_id)
        return state and state["lease_owner"] == "worker-a" and state["fencing_token"] == 1 and state["state"] == "running"

    wait_until(worker_a_owns_first, timeout=20, label="worker-a to become first claimer with fencing token 1")

    time.sleep(lease_expiry_buffer())

    worker_b = subprocess.Popen(b_cmd, env=b_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    worker_a_log, _ = worker_a.communicate(timeout=30)
    worker_b_log, _ = worker_b.communicate(timeout=30)

    final_state = fetch_job(job_id)
    artifact = write_artifact(job_id, worker_a_log, worker_b_log, final_state)

    assert final_state is not None
    assert final_state["state"] == "succeeded"
    assert final_state["fencing_token"] >= 2, f"expected reclaim to advance fencing token, got {final_state}"
    assert "stale" in worker_a_log.lower() or "fence" in worker_a_log.lower() or "reject" in worker_a_log.lower(), (
        f"worker-a log does not show stale/fencing rejection; artifact={artifact}\n{worker_a_log}"
    )


def lease_expiry_buffer():
    raw = os.getenv("LEASE_RACE_WAIT_SECONDS", "7")
    return float(raw)

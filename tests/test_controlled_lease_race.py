import json
import hashlib
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
    payload_obj = {"kind": "lease_race_test"}
    payload_json = json.dumps(payload_obj, sort_keys=True)
    payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()

    cur.execute(
        """
        INSERT INTO jobs (
            id, payload_hash, payload, state, attempts, max_attempts,
            fencing_token, created_at, updated_at, lease_owner, lease_expires_at, last_error
        )
        VALUES (%s, %s, %s::jsonb, 'queued', 0, 3, 0, NOW(), NOW(), NULL, NULL, NULL)
        ON CONFLICT (id) DO UPDATE
        SET payload_hash = EXCLUDED.payload_hash,
            payload = EXCLUDED.payload,
            state='queued',
            attempts=0,
            max_attempts=3,
            fencing_token=0,
            lease_owner=NULL,
            lease_expires_at=NULL,
            last_error=NULL,
            updated_at=NOW()
        """,
        (job_id, payload_hash, payload_json),
    )


def fetch_job(job_id):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, state, lease_owner, fencing_token,
                       lease_expires_at, attempts, last_error
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
                "attempts": row[5],
                "last_error": row[6],
            }


def worker_cmd(worker_id, job_id, hold_seconds):
    env = os.environ.copy()

    # CRITICAL: propagate DB connection
    env.setdefault("DATABASE_URL", "postgresql://faultline:faultline@localhost:5432/faultline")

    env["FAULTLINE_WORKER_ID"] = worker_id
    env["WORKER_ID"] = worker_id
    env["CLAIM_JOB_ID"] = job_id
    env["LEASE_SECONDS"] = "3"
    env["WORK_SLEEP_SECONDS"] = str(hold_seconds)

    # Disable metrics server to avoid port collision
    env["METRICS_ENABLED"] = "0"

    env["EXIT_ON_SUCCESS"] = "1"
    env["EXIT_ON_STALE"] = "1"
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
    job_id = str(uuid.uuid4())

    with db() as conn:
        with conn.cursor() as cur:
            seed_job(cur, job_id)
        conn.commit()

    a_cmd, a_env = worker_cmd("worker-a", job_id, hold_seconds=8)
    b_cmd, b_env = worker_cmd("worker-b", job_id, hold_seconds=0)

    worker_a = subprocess.Popen(a_cmd, env=a_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    time.sleep(1)
    if worker_a.poll() is not None:
        worker_a_log, _ = worker_a.communicate()
        raise AssertionError(f"worker-a exited before first claim\n{worker_a_log}")

    last_seen = {"state": None}

    def worker_a_owns_first():
        state = fetch_job(job_id)
        last_seen["state"] = state
        return state and state["lease_owner"] == "worker-a" and state["fencing_token"] == 1 and state["state"] == "running"

    try:
        wait_until(worker_a_owns_first, timeout=20, label="worker-a to become first claimer with fencing token 1")
    except AssertionError:
        worker_a.terminate()
        worker_a_log, _ = worker_a.communicate(timeout=10)
        raise AssertionError(
            "Timed out waiting for worker-a first claim\n"
            f"last db state={last_seen['state']}\n\n"
            f"worker-a log:\n{worker_a_log}"
        )

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
    raw = os.getenv("LEASE_RACE_WAIT_SECONDS", "4")
    return float(raw)

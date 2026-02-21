import os
import uuid
import hashlib
import subprocess
import time
import psycopg2

WORKER_CMD = ["python", "services/worker/worker.py"]


def _payload_hash(payload_str: str) -> str:
    return hashlib.sha256(payload_str.encode("utf-8")).hexdigest()


def _db(url):
    return psycopg2.connect(url)


def _ensure_barriers(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS barriers (
          name TEXT PRIMARY KEY,
          opened_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """
    )


def _reset_barriers(cur):
    _ensure_barriers(cur)
    cur.execute("TRUNCATE TABLE barriers")


def _seed_job(cur, job_id):
    payload = "{}"
    cur.execute(
        """
        INSERT INTO jobs (id, payload, payload_hash, state, attempts, max_attempts, next_run_at)
        VALUES (%s, %s, %s, 'queued', 0, 5, NOW() + INTERVAL '1 day')
        """,
        (job_id, payload, _payload_hash(payload)),
    )


def _wait_job_state(database_url, job_id, want, timeout_s=10):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        with _db(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT state FROM jobs WHERE id=%s", (job_id,))
                row = cur.fetchone()
                if row and row[0] == want:
                    return True
        time.sleep(0.2)
    return False


def _wait_barrier_open(database_url, name, timeout_s=10):
    """
    Determinism helper:
    Ensure worker A has opened the barrier row before worker B starts.
    Prevents flaky runs where worker B claims first and waits forever.
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        with _db(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM barriers WHERE name=%s", (name,))
                if cur.fetchone():
                    return True
        time.sleep(0.05)
    return False


def test_lease_expiry_race_is_blocked_by_fencing(database_url):
    job_id = str(uuid.uuid4())

    with _db(database_url) as conn:
        with conn.cursor() as cur:
            _reset_barriers(cur)
            _seed_job(cur, job_id)

    base_env = os.environ.copy()
    base_env["DATABASE_URL"] = database_url
    base_env["LEASE_SECONDS"] = "1"
    base_env["BARRIER_TIMEOUT_S"] = "30"
    base_env["PYTHONUNBUFFERED"] = "1"
    base_env["METRICS_ENABLED"] = "0"
    base_env["CLAIM_JOB_ID"] = job_id

    env_a = base_env.copy()
    env_a["BARRIER_OPEN"] = "after_lease_acquire"
    env_a["WORK_SLEEP_SECONDS"] = "2.5"
    env_a["MAX_LOOPS"] = "200"
    env_a["EXIT_ON_STALE"] = "1"

    env_b = base_env.copy()
    env_b["BARRIER_WAIT"] = "after_lease_acquire"
    env_b["WORK_SLEEP_SECONDS"] = "0"
    env_b["MAX_LOOPS"] = "800"
    env_b["EXIT_ON_SUCCESS"] = "1"

    # Start A first so it reliably claims and opens the barrier.
    p_a = subprocess.Popen(
        WORKER_CMD,
        env=env_a,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    # Ensure barrier exists before starting B (eliminates flaky barrier_timeout).
    assert _wait_barrier_open(database_url, "after_lease_acquire", timeout_s=10)

    p_b = subprocess.Popen(
        WORKER_CMD,
        env=env_b,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    out_a, _ = p_a.communicate(timeout=60)
    out_b, _ = p_b.communicate(timeout=60)

    # Always write logs to disk so you can extract an HN snippet even if asserts fail.
    with open("/tmp/lease_race_worker_a.log", "w") as f:
        f.write(out_a)
    with open("/tmp/lease_race_worker_b.log", "w") as f:
        f.write(out_b)

    assert "lease_acquired" in out_a
    assert "stale_write_blocked" in out_a
    assert '"reason": "success"' in out_b

    assert _wait_job_state(database_url, job_id, "succeeded", timeout_s=10)

    with _db(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*), MIN(fencing_token), MAX(fencing_token) "
                "FROM ledger_entries WHERE job_id=%s",
                (job_id,),
            )
            count, min_tok, max_tok = cur.fetchone()
            assert count == 1
            assert int(min_tok) == int(max_tok)
            assert int(min_tok) >= 2
            
            
def _wait_barrier_open(database_url, name, timeout_s=10):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        with _db(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM barriers WHERE name=%s", (name,))
                if cur.fetchone():
                    return True
        time.sleep(0.05)
    return False
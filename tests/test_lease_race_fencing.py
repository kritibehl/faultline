import os
import uuid
import hashlib
import subprocess
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

    env_a = base_env.copy()
    env_a["BARRIER_OPEN"] = "after_lease_acquire"
    env_a["WORK_SLEEP_SECONDS"] = "2.5"
    env_a["MAX_LOOPS"] = "60"
    env_a["EXIT_ON_STALE"] = "1"

    env_b = base_env.copy()
    env_b["BARRIER_WAIT"] = "after_lease_acquire"
    env_b["WORK_SLEEP_SECONDS"] = "0"
    env_b["MAX_LOOPS"] = "300"
    env_b["EXIT_ON_SUCCESS"] = "1"

    p_a = subprocess.Popen(WORKER_CMD, env=env_a, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    p_b = subprocess.Popen(WORKER_CMD, env=env_b, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    out_a, _ = p_a.communicate(timeout=60)
    out_b, _ = p_b.communicate(timeout=60)

    assert "stale_write_blocked" in out_a, out_a
    assert "lease_acquired" in out_b, out_b

    with _db(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT state, fencing_token FROM jobs WHERE id=%s", (job_id,))
            state, token = cur.fetchone()
            assert state == "succeeded"
            assert int(token) >= 2

            cur.execute(
                "SELECT COUNT(*), MIN(fencing_token), MAX(fencing_token) "
                "FROM ledger_entries WHERE job_id=%s",
                (job_id,),
            )
            count, min_tok, max_tok = cur.fetchone()
            assert count == 1
            assert int(min_tok) == int(max_tok)
            assert int(min_tok) >= 2
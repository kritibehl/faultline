from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

import psycopg2


DATABASE_URL = os.environ.get(
    "DEMO_DATABASE_URL",
    "postgresql://faultline:faultline@localhost:55432/faultline_demo",
)


def log(event: str, **fields) -> None:
    print(json.dumps({
        "event": event,
        "ts": datetime.now(timezone.utc).isoformat(),
        **fields,
    }, indent=2))


def reset_demo(cur) -> None:
    cur.execute("DELETE FROM demo_commit_log")
    cur.execute("DELETE FROM demo_jobs")
    cur.execute("DELETE FROM demo_workers")
    cur.execute("INSERT INTO demo_workers(worker_id, status) VALUES ('worker-a', 'idle'), ('worker-b', 'idle')")
    cur.execute(
        """
        INSERT INTO demo_jobs(job_id, payload, state)
        VALUES ('job-stale-race-1', '{"task":"send_receipt"}', 'queued')
        """
    )


def claim_job(cur, worker_id: str, lease_seconds: int):
    cur.execute(
        """
        WITH candidate AS (
            SELECT job_id
            FROM demo_jobs
            WHERE state = 'queued'
               OR (state = 'running' AND lease_expires_at < NOW())
            ORDER BY updated_at
            LIMIT 1
            FOR UPDATE SKIP LOCKED
        )
        UPDATE demo_jobs
        SET state='running',
            lease_owner=%s,
            lease_expires_at=NOW() + make_interval(secs => %s),
            fencing_token=fencing_token + 1,
            updated_at=NOW()
        WHERE job_id IN (SELECT job_id FROM candidate)
        RETURNING job_id, fencing_token, lease_owner, lease_expires_at
        """,
        (worker_id, lease_seconds),
    )
    return cur.fetchone()


def commit_result(cur, job_id: str, worker_id: str, fencing_token: int):
    cur.execute(
        """
        SELECT fencing_token, lease_owner
        FROM demo_jobs
        WHERE job_id=%s
        FOR UPDATE
        """,
        (job_id,),
    )
    current_token, lease_owner = cur.fetchone()

    if int(current_token) != int(fencing_token):
        log(
            "reject_stale_write",
            job_id=job_id,
            worker_id=worker_id,
            attempted_fencing_token=fencing_token,
            current_fencing_token=current_token,
            lease_owner=lease_owner,
        )
        return False

    cur.execute(
        """
        INSERT INTO demo_commit_log(job_id, worker_id, fencing_token, result)
        VALUES (%s, %s, %s, '{"status":"ok"}')
        ON CONFLICT(job_id) DO NOTHING
        RETURNING commit_id
        """,
        (job_id, worker_id, fencing_token),
    )
    inserted = cur.fetchone()

    cur.execute(
        """
        UPDATE demo_jobs
        SET state='succeeded',
            lease_owner=NULL,
            lease_expires_at=NULL,
            updated_at=NOW()
        WHERE job_id=%s
        """,
        (job_id,),
    )

    log(
        "commit_result",
        job_id=job_id,
        worker_id=worker_id,
        fencing_token=fencing_token,
        inserted=bool(inserted),
    )
    return bool(inserted)


def main() -> None:
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            reset_demo(cur)
        conn.commit()

    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            row_a = claim_job(cur, "worker-a", lease_seconds=1)
            log("claim_job", worker_id="worker-a", row=row_a)
        conn.commit()

    time.sleep(1.3)

    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            row_b = claim_job(cur, "worker-b", lease_seconds=30)
            log("lease_takeover", worker_id="worker-b", row=row_b)
        conn.commit()

    job_id = row_b[0]
    token_b = int(row_b[1])
    token_a = int(row_a[1])

    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            commit_result(cur, job_id, "worker-b", token_b)
        conn.commit()

    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            accepted = commit_result(cur, job_id, "worker-a", token_a)
            log("stale_worker_late_commit_attempt", accepted=accepted)
        conn.commit()

    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT job_id, state, fencing_token FROM demo_jobs")
            jobs = cur.fetchall()
            cur.execute("SELECT job_id, worker_id, fencing_token FROM demo_commit_log")
            commits = cur.fetchall()

    log("final_state", jobs=jobs, commits=commits)


if __name__ == "__main__":
    main()

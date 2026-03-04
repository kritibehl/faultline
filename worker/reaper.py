"""
worker/reaper.py
─────────────────
Expired lease reaper for Faultline.

The reaper handles the primary crash recovery path: jobs whose worker
died mid-execution and never committed OR never updated state, leaving
the job stuck in 'running' with an expired lease.

Two complementary recovery mechanisms exist:

    1. REAPER (this module)
       Detects jobs in state='running' with lease_expires_at < NOW()
       and resets them to state='queued' so a new worker can reclaim them.
       This is the fast path — triggered within REAP_INTERVAL_SECONDS.

    2. RECONCILER (services/worker/reconciler.py)
       Detects jobs with a committed ledger entry but state != 'succeeded'.
       This covers the narrow window where the ledger INSERT committed
       but the jobs UPDATE had not yet run when the worker crashed.

Together these two mechanisms guarantee state convergence: every job
eventually reaches a terminal state (succeeded or failed), regardless
of how and when workers crash.

Usage
─────
The reaper runs as a background thread inside the worker process, or
can be run as a standalone process for higher reap throughput.

    from worker.reaper import reap_expired_leases

    recovered = reap_expired_leases(cur)
    # recovered = list of job IDs that were reset to 'queued'
"""

import json
import os
import time
from datetime import datetime, timezone

import psycopg2
from psycopg2 import OperationalError

REAP_INTERVAL_SECONDS = int(os.environ.get("REAP_INTERVAL_SECONDS", "10"))
REAP_BATCH_SIZE = int(os.environ.get("REAP_BATCH_SIZE", "100"))


def _log(event, **fields):
    print(json.dumps({
        "event": event,
        "ts": datetime.now(timezone.utc).isoformat(),
        **fields,
    }), flush=True)


def reap_expired_leases(cur) -> list:
    """
    Reset jobs stuck in 'running' with an expired lease back to 'queued'.

    A job is eligible for reaping when:
        state = 'running'  AND  lease_expires_at < NOW()

    This condition means the worker holding the lease has either:
        - Crashed (most common)
        - Stalled long enough for the lease to expire
        - Lost DB connectivity

    The fencing_token is NOT incremented here. The next worker to claim
    the job will increment it via claim_one_job(), advancing the epoch.
    Any writes from the previous worker carrying the old token will be
    rejected by assert_fence() or the fencing_token WHERE clause.

    Uses FOR UPDATE SKIP LOCKED so multiple reapers can run concurrently.

    Returns list of reaped job IDs.
    """
    cur.execute(
        """
        WITH expired AS (
            SELECT id, lease_owner, fencing_token
            FROM jobs
            WHERE state = 'running'
              AND lease_expires_at IS NOT NULL
              AND lease_expires_at < NOW()
            ORDER BY lease_expires_at
            LIMIT %s
            FOR UPDATE SKIP LOCKED
        )
        UPDATE jobs
        SET state            = 'queued',
            lease_owner      = NULL,
            lease_expires_at = NULL,
            next_run_at      = NOW(),
            updated_at       = NOW()
        WHERE id IN (SELECT id FROM expired)
        RETURNING id, (SELECT lease_owner FROM expired WHERE expired.id = jobs.id),
                       (SELECT fencing_token FROM expired WHERE expired.id = jobs.id)
        """,
        (REAP_BATCH_SIZE,),
    )
    rows = cur.fetchall()

    for job_id, stale_owner, token in rows:
        _log(
            "lease_reaped",
            job_id=str(job_id),
            stale_owner=stale_owner,
            fencing_token=token,
        )

    return [r[0] for r in rows]


def get_conn(database_url=None):
    url = database_url or os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg2.connect(url)


if __name__ == "__main__":
    """Run as a standalone reaper process."""
    _log("reaper_started", interval=REAP_INTERVAL_SECONDS, batch_size=REAP_BATCH_SIZE)

    while True:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    reaped = reap_expired_leases(cur)
                    if reaped:
                        _log("reap_batch_complete", count=len(reaped))
        except OperationalError as e:
            _log("reaper_db_error", error=str(e))
            time.sleep(2)

        time.sleep(REAP_INTERVAL_SECONDS)
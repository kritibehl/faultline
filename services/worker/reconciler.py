import os
import time
import psycopg2
from psycopg2 import OperationalError

DATABASE_URL = os.environ["DATABASE_URL"]

BATCH_SIZE = int(os.environ.get("RECONCILE_BATCH_SIZE", "100"))
SLEEP_SECONDS = int(os.environ.get("RECONCILE_SLEEP_SECONDS", "5"))


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def reconcile_once(cur):
    """
    Converge jobs.state to succeeded when a ledger entry already exists.

    Repairs the classic crash window:
      - ledger insert committed
      - worker died before updating jobs.state
    """
    cur.execute(
        """
        WITH candidates AS (
            SELECT j.id
            FROM jobs j
            JOIN ledger_entries l
              ON l.job_id = j.id
            WHERE j.state <> 'succeeded'
            ORDER BY j.updated_at NULLS FIRST
            LIMIT %s
            FOR UPDATE SKIP LOCKED
        )
        UPDATE jobs
        SET
            state = 'succeeded',
            lease_owner = NULL,
            lease_expires_at = NULL,
            next_run_at = NULL,
            updated_at = NOW()
        WHERE id IN (SELECT id FROM candidates)
        RETURNING id
        """,
        (BATCH_SIZE,),
    )
    rows = cur.fetchall()
    return [r[0] for r in rows]


if __name__ == "__main__":
    while True:
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    repaired = reconcile_once(cur)
                    if repaired:
                        print(f"reconciled {len(repaired)} jobs")
        except OperationalError:
            # DB down / transient network failure
            time.sleep(2)

        time.sleep(SLEEP_SECONDS)

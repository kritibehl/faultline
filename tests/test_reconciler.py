import os
import time
import psycopg2
from psycopg2 import OperationalError

BATCH_SIZE = int(os.environ.get("RECONCILE_BATCH_SIZE", "100"))
SLEEP_SECONDS = int(os.environ.get("RECONCILE_SLEEP_SECONDS", "5"))


def get_conn(database_url: str | None = None):
    """
    Import-safe: DATABASE_URL is read at runtime, not import time.
    Allows unit/integration tests to import this module without env configured.
    """
    url = database_url or os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg2.connect(url)


def reconcile_once(cur):
    """
    Converge jobs.state to succeeded when a ledger entry already exists.
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
                        print(f"reconciled {len(repaired)} jobs", flush=True)
        except OperationalError:
            time.sleep(2)
        except RuntimeError as e:
            # Missing DATABASE_URL etc.
            print(str(e), flush=True)
            time.sleep(2)

        time.sleep(SLEEP_SECONDS)
import psycopg2
import uuid
import os

from services.worker.reconciler import reconcile_once

DATABASE_URL = os.environ["DATABASE_URL"]


def test_reconciler_repairs_incomplete_state():
    job_id = str(uuid.uuid4())

    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Seed job in wrong state
            cur.execute(
                """
                INSERT INTO jobs (id, state)
                VALUES (%s, 'running')
                """,
                (job_id,),
            )

            # Ledger entry exists (apply succeeded earlier)
            cur.execute(
                """
                INSERT INTO ledger_entries (job_id, account_id, delta)
                VALUES (%s, 'test', 1)
                """,
                (job_id,),
            )

            # Run reconciler
            repaired = reconcile_once(cur)

            assert job_id in repaired

            # Verify job converged
            cur.execute(
                "SELECT state FROM jobs WHERE id = %s",
                (job_id,),
            )
            state = cur.fetchone()[0]

            assert state == "succeeded"

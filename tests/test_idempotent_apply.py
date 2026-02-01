import psycopg2
import uuid
import os

DATABASE_URL = os.environ["DATABASE_URL"]


def test_idempotent_apply():
    job_id = str(uuid.uuid4())

    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Seed job
            cur.execute(
                """
                INSERT INTO jobs (id, state)
                VALUES (%s, 'running')
                """,
                (job_id,),
            )

            # First apply
            cur.execute(
                """
                INSERT INTO ledger_entries (job_id, account_id, delta)
                VALUES (%s, 'test', 1)
                ON CONFLICT DO NOTHING
                """,
                (job_id,),
            )

            # Second apply (retry)
            cur.execute(
                """
                INSERT INTO ledger_entries (job_id, account_id, delta)
                VALUES (%s, 'test', 1)
                ON CONFLICT DO NOTHING
                """,
                (job_id,),
            )

            # Assert exactly one ledger entry
            cur.execute(
                "SELECT COUNT(*) FROM ledger_entries WHERE job_id = %s",
                (job_id,),
            )
            count = cur.fetchone()[0]

            assert count == 1

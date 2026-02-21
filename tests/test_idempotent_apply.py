import uuid
import psycopg2


def test_idempotent_apply(database_url):
    job_id = str(uuid.uuid4())

    with psycopg2.connect(database_url) as conn:
        with conn.cursor() as cur:
            # Seed job (keep minimal; assumes defaults exist for other cols)
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
                INSERT INTO ledger_entries (job_id, fencing_token, account_id, delta)
                VALUES (%s, %s, 'test', 1)
                ON CONFLICT (job_id, fencing_token) DO NOTHING
                """,
                (job_id, 1),
            )

            # Second apply (same token retry)
            cur.execute(
                """
                INSERT INTO ledger_entries (job_id, fencing_token, account_id, delta)
                VALUES (%s, %s, 'test', 1)
                ON CONFLICT (job_id, fencing_token) DO NOTHING
                """,
                (job_id, 1),
            )

            cur.execute(
                "SELECT COUNT(*) FROM ledger_entries WHERE job_id=%s AND fencing_token=%s",
                (job_id, 1),
            )
            count = cur.fetchone()[0]
            assert count == 1
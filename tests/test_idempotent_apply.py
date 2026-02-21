import uuid
import psycopg2


def test_idempotent_apply(database_url):
    job_id = str(uuid.uuid4())

    with psycopg2.connect(database_url) as conn:
        with conn.cursor() as cur:
            # payload is NOT NULL in your schema
            cur.execute(
                """
                INSERT INTO jobs (id, payload, state, attempts, max_attempts)
                VALUES (%s, %s, 'running', 0, 5)
                """,
                (job_id, "{}"),
            )

            # Apply twice for same (job_id, fencing_token) => single row
            cur.execute(
                """
                INSERT INTO ledger_entries (job_id, fencing_token, account_id, delta)
                VALUES (%s, %s, 'test', 1)
                ON CONFLICT (job_id, fencing_token) DO NOTHING
                """,
                (job_id, 1),
            )

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

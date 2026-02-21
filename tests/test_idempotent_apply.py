import uuid
import hashlib
import psycopg2


def _payload_hash(payload_str: str) -> str:
    return hashlib.sha256(payload_str.encode("utf-8")).hexdigest()


def test_idempotent_apply(database_url):
    job_id = str(uuid.uuid4())
    payload = "{}"
    payload_hash = _payload_hash(payload)

    with psycopg2.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO jobs (id, payload, payload_hash, state, attempts, max_attempts)
                VALUES (%s, %s, %s, 'running', 0, 5)
                """,
                (job_id, payload, payload_hash),
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
            assert cur.fetchone()[0] == 1
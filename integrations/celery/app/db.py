from __future__ import annotations

import os

import psycopg


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://faultline:faultline@postgres:5432/faultline",
)


def connect():
    return psycopg.connect(DATABASE_URL)


def next_token(job_id: str) -> int:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO job_ownership(job_id, current_token)
                VALUES (%s, 1)
                ON CONFLICT (job_id)
                DO UPDATE
                SET current_token = job_ownership.current_token + 1
                RETURNING current_token
                """,
                (job_id,),
            )
            token = cur.fetchone()[0]

        conn.commit()

    return int(token)


def record_attempt(
    job_id: str,
    worker_name: str,
    token: int,
    phase: str,
) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO attempts(
                    job_id,
                    worker_name,
                    fencing_token,
                    phase
                )
                VALUES (%s, %s, %s, %s)
                """,
                (job_id, worker_name, token, phase),
            )

        conn.commit()


def unsafe_commit(
    job_id: str,
    worker_name: str,
    token: int,
    amount: int,
) -> bool:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO effects(
                    job_id,
                    worker_name,
                    fencing_token,
                    amount
                )
                VALUES (%s, %s, %s, %s)
                """,
                (job_id, worker_name, token, amount),
            )

        conn.commit()

    return True


def fenced_commit(
    job_id: str,
    worker_name: str,
    token: int,
    amount: int,
) -> bool:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT current_token
                FROM job_ownership
                WHERE job_id = %s
                FOR UPDATE
                """,
                (job_id,),
            )

            row = cur.fetchone()

            if row is None:
                raise RuntimeError(f"missing ownership row for {job_id}")

            current_token = int(row[0])

            if token != current_token:
                cur.execute(
                    """
                    INSERT INTO stale_rejections(
                        job_id,
                        worker_name,
                        presented_token,
                        current_token
                    )
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        job_id,
                        worker_name,
                        token,
                        current_token,
                    ),
                )

                conn.commit()
                return False

            cur.execute(
                """
                INSERT INTO effects(
                    job_id,
                    worker_name,
                    fencing_token,
                    amount
                )
                VALUES (%s, %s, %s, %s)
                """,
                (
                    job_id,
                    worker_name,
                    token,
                    amount,
                ),
            )

        conn.commit()

    return True

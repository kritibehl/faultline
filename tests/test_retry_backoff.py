"""
tests/test_retry_backoff.py
────────────────────────────
Validates bounded retry with exponential backoff.
"""

import hashlib
import sys
import os
import time
import uuid

import psycopg2
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.worker.retry import backoff_seconds, mark_for_retry


def _payload_hash(s="{}"):
    return hashlib.sha256(s.encode()).hexdigest()


def _seed_job(cur, job_id, max_attempts=3):
    cur.execute(
        """
        INSERT INTO jobs (id, payload, payload_hash, state, attempts, max_attempts, next_run_at)
        VALUES (%s, '{}', %s, 'queued', 0, %s, NOW())
        """,
        (job_id, _payload_hash(), max_attempts),
    )


def _get_job(cur, job_id):
    cur.execute(
        "SELECT state, attempts, max_attempts, next_run_at, last_error FROM jobs WHERE id=%s",
        (job_id,),
    )
    return cur.fetchone()


def test_retry_on_failure_schedules_backoff(database_url):
    """After a failure, job is rescheduled with next_run_at in the future."""
    job_id = str(uuid.uuid4())

    with psycopg2.connect(database_url) as conn:
        with conn.cursor() as cur:
            _seed_job(cur, job_id, max_attempts=3)
            cur.execute(
                "UPDATE jobs SET state='running', fencing_token=1, "
                "lease_owner='test', lease_expires_at=NOW()+interval '30s' WHERE id=%s",
                (job_id,),
            )
            mark_for_retry(cur, job_id, 1, attempts=0, max_attempts=3,
                           error_msg="simulated_execution_failure")
            state, attempts, _, next_run_at, last_error = _get_job(cur, job_id)

    assert state == "queued"
    assert attempts == 1
    assert next_run_at is not None
    assert last_error == "simulated_execution_failure"


def test_backoff_increases_exponentially():
    """Backoff formula: min(base * 2^(attempts-1), cap=300)."""
    cases = [
        (1, 2.0), (2, 4.0), (3, 8.0), (4, 16.0), (5, 32.0),
        (6, 64.0), (7, 128.0), (8, 256.0), (9, 300.0), (10, 300.0),
    ]
    for attempts, expected in cases:
        result = backoff_seconds(attempts)
        assert result == expected, f"attempts={attempts}: expected {expected}s got {result}s"


def test_max_attempts_marks_failed(database_url):
    """When new_attempts >= max_attempts, state becomes 'failed'."""
    job_id = str(uuid.uuid4())

    with psycopg2.connect(database_url) as conn:
        with conn.cursor() as cur:
            _seed_job(cur, job_id, max_attempts=3)
            cur.execute(
                "UPDATE jobs SET state='running', fencing_token=2, attempts=2, "
                "lease_owner='test', lease_expires_at=NOW()+interval '30s' WHERE id=%s",
                (job_id,),
            )
            outcome = mark_for_retry(cur, job_id, 2, attempts=2, max_attempts=3,
                                     error_msg="final_failure")
            state, attempts_col, _, next_run_at, last_error = _get_job(cur, job_id)

    assert outcome == "failed"
    assert state == "failed"
    assert attempts_col == 3
    assert next_run_at is None
    assert last_error == "final_failure"


def test_next_run_at_is_in_future(database_url):
    """next_run_at must be strictly in the future — worker cannot immediately re-claim."""
    job_id = str(uuid.uuid4())
    before = time.time()

    with psycopg2.connect(database_url) as conn:
        with conn.cursor() as cur:
            _seed_job(cur, job_id, max_attempts=5)
            cur.execute(
                "UPDATE jobs SET state='running', fencing_token=1, "
                "lease_owner='test', lease_expires_at=NOW()+interval '30s' WHERE id=%s",
                (job_id,),
            )
            mark_for_retry(cur, job_id, 1, attempts=0, max_attempts=5,
                           error_msg="transient_error")
            cur.execute("SELECT next_run_at FROM jobs WHERE id=%s", (job_id,))
            next_run_at = cur.fetchone()[0]

    assert next_run_at is not None
    assert next_run_at.timestamp() > before + 1


def test_retry_backoff_all_attempts(database_url):
    """Full lifecycle: job fails every attempt, each retry increments attempts and grows backoff."""
    job_id = str(uuid.uuid4())
    MAX = 4

    with psycopg2.connect(database_url) as conn:
        with conn.cursor() as cur:
            _seed_job(cur, job_id, max_attempts=MAX)

            for attempt in range(MAX):
                cur.execute(
                    """
                    UPDATE jobs SET state='running', fencing_token=fencing_token+1,
                        lease_owner='test', lease_expires_at=NOW()+interval '30s'
                    WHERE id=%s
                      AND (state='queued' OR (state='running' AND lease_expires_at<NOW()))
                    RETURNING fencing_token
                    """,
                    (job_id,),
                )
                row = cur.fetchone()
                assert row, f"Could not claim on attempt {attempt}"
                token = int(row[0])

                outcome = mark_for_retry(cur, job_id, token, attempts=attempt,
                                         max_attempts=MAX, error_msg=f"fail_{attempt}")
                state, attempts_col, _, next_run_at, _ = _get_job(cur, job_id)

                if attempt < MAX - 1:
                    assert outcome == "retry"
                    assert state == "queued"
                    assert attempts_col == attempt + 1
                    assert next_run_at is not None
                    cur.execute(
                        "UPDATE jobs SET next_run_at=NOW()-interval '1s' WHERE id=%s",
                        (job_id,),
                    )
                else:
                    assert outcome == "failed"
                    assert state == "failed"
                    assert attempts_col == MAX
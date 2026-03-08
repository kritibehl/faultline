import os

BACKOFF_BASE_SECONDS = float(os.getenv("BACKOFF_BASE_SECONDS", "2"))
BACKOFF_MAX_SECONDS = float(os.getenv("BACKOFF_MAX_SECONDS", "300"))


def backoff_seconds(attempts: int, base: float = None, cap: float = None) -> float:
    b = base if base is not None else BACKOFF_BASE_SECONDS
    c = cap if cap is not None else BACKOFF_MAX_SECONDS
    return min(b * (2 ** (attempts - 1)), c)


def mark_for_retry(cur, job_id: str, token: int, attempts: int,
                   max_attempts: int, error_msg: str = "") -> str:
    new_attempts = attempts + 1
    if new_attempts >= max_attempts:
        cur.execute(
            """
            UPDATE jobs
            SET state='failed', lease_owner=NULL, lease_expires_at=NULL,
                attempts=%s, last_error=%s, updated_at=NOW()
            WHERE id=%s AND fencing_token=%s
            """,
            (new_attempts, error_msg[:1000] if error_msg else None, job_id, token),
        )
        return "failed"
    else:
        delay = backoff_seconds(new_attempts)
        cur.execute(
            """
            UPDATE jobs
            SET state='queued', lease_owner=NULL, lease_expires_at=NULL,
                attempts=%s, last_error=%s,
                next_run_at=NOW() + make_interval(secs => %s), updated_at=NOW()
            WHERE id=%s AND fencing_token=%s
            """,
            (new_attempts, error_msg[:1000] if error_msg else None,
             delay, job_id, token),
        )
        return "retry"

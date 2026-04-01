from services.common.tracing import init_tracing, get_tracer, start_span
from datetime import datetime, timezone, timedelta

init_tracing("faultline-retry")
tracer = get_tracer("faultline.retry")


def backoff_seconds(attempt: int) -> int:
    return min(2 ** attempt, 30)


def _otel_retry_backoff_span(job_id, attempt, delay_seconds):
    with start_span(
        tracer,
        "retry.backoff",
        job_id=str(job_id),
        attempt=int(attempt),
        delay_ms=int(delay_seconds * 1000),
    ):
        pass


def mark_for_retry(cur, job_id, token, attempts, max_attempts, last_error):
    if attempts + 1 >= max_attempts:
        cur.execute(
            """
            UPDATE jobs
            SET state='failed', lease_owner=NULL, lease_expires_at=NULL,
                last_error=%s, updated_at=NOW()
            WHERE id=%s AND fencing_token=%s
            """,
            (last_error, job_id, token),
        )
        return "failed"

    delay = backoff_seconds(attempts + 1)
    _otel_retry_backoff_span(job_id, attempts + 1, delay)

    cur.execute(
        """
        UPDATE jobs
        SET state='queued', lease_owner=NULL, lease_expires_at=NULL,
            available_at=%s, last_error=%s, updated_at=NOW()
        WHERE id=%s AND fencing_token=%s
        """,
        (datetime.now(timezone.utc) + timedelta(seconds=delay), last_error, job_id, token),
    )
    return "retried"

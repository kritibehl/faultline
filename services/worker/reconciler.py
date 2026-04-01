from services.common.tracing import init_tracing, get_tracer, start_span
import os
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]

init_tracing("faultline-reconciler")
tracer = get_tracer("faultline.reconciler")


def _otel_recover_span(job_id, orphan_age_seconds):
    with start_span(
        tracer,
        "reconciler.recover",
        job_id=str(job_id),
        orphan_age=float(orphan_age_seconds),
    ):
        pass


def reclaim_expired_jobs():
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, EXTRACT(EPOCH FROM (NOW() - lease_expires_at)) AS orphan_age_seconds
                FROM jobs
                WHERE state='running'
                  AND lease_expires_at IS NOT NULL
                  AND lease_expires_at < NOW()
                """
            )
            rows = cur.fetchall()

            for job_id, orphan_age_seconds in rows:
                _otel_recover_span(job_id, orphan_age_seconds)
                cur.execute(
                    """
                    UPDATE jobs
                    SET state='queued',
                        lease_owner = NULL,
                        lease_expires_at = NULL,
                        updated_at = NOW()
                    WHERE id=%s
                    """,
                    (job_id,),
                )
        conn.commit()


if __name__ == "__main__":
    reclaim_expired_jobs()

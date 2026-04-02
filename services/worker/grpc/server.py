"""Minimal gRPC facade for Faultline job submission / claim / completion.

This is intentionally thin: the goal is not to duplicate the worker runtime,
but to expose a network boundary that makes exactly-once / fencing behavior
observable across service-to-service communication.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from concurrent import futures

import grpc

from common.observability.tracing import get_tracer
from services.worker.transport_db import get_conn
from services.worker.spans import start_span

# Generated at build time from worker.proto.
from services.worker.grpc import worker_pb2, worker_pb2_grpc  # type: ignore

PORT = int(os.getenv("FAULTLINE_GRPC_PORT", "50051"))
tracer = get_tracer("faultline.grpc")


def _payload_hash(payload: str) -> str:
    return hashlib.sha256(payload.encode()).hexdigest()


class FaultlineWorkerService(worker_pb2_grpc.FaultlineWorkerServicer):
    def SubmitJob(self, request, context):
        with start_span(tracer, "grpc.submit"):
            job_id = str(uuid.uuid4())
            payload = request.payload or "{}"
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO jobs (
                            id, payload, payload_hash, state, attempts, max_attempts,
                            lease_owner, lease_expires_at, fencing_token, next_run_at
                        )
                        VALUES (%s, %s, %s, 'queued', 0, 5, NULL, NULL, 0, NOW())
                        """,
                        (job_id, payload, _payload_hash(payload)),
                    )
                    conn.commit()
            return worker_pb2.SubmitJobResponse(job_id=job_id, state="queued")

    def ClaimNextJob(self, request, context):
        force_job_id = request.force_job_id or None
        with start_span(tracer, "grpc.claim"):
            with get_conn() as conn:
                with conn.cursor() as cur:
                    if force_job_id:
                        cur.execute(
                            """
                            UPDATE jobs
                            SET state='running',
                                lease_owner=%s,
                                lease_expires_at = NOW() + make_interval(secs => %s),
                                fencing_token=fencing_token+1,
                                updated_at=NOW()
                            WHERE id=%s
                              AND (
                                    state='queued'
                                 OR (state='running' AND lease_expires_at < NOW())
                              )
                            RETURNING id, payload, fencing_token, lease_owner
                            """,
                            (request.worker_id, int(request.lease_seconds or 30), force_job_id),
                        )
                    else:
                        cur.execute(
                            """
                            UPDATE jobs
                            SET state='running',
                                lease_owner=%s,
                                lease_expires_at = NOW() + make_interval(secs => %s),
                                fencing_token=fencing_token+1,
                                updated_at=NOW()
                            WHERE id = (
                                SELECT id
                                FROM jobs
                                WHERE (state='queued' AND (next_run_at IS NULL OR next_run_at <= NOW()))
                                   OR (state='running' AND lease_expires_at < NOW())
                                ORDER BY COALESCE(next_run_at, created_at)
                                FOR UPDATE SKIP LOCKED
                                LIMIT 1
                            )
                            RETURNING id, payload, fencing_token, lease_owner
                            """,
                            (request.worker_id, int(request.lease_seconds or 30)),
                        )
                    row = cur.fetchone()
                    conn.commit()
            if not row:
                return worker_pb2.ClaimNextJobResponse(claimed=False)
            return worker_pb2.ClaimNextJobResponse(
                claimed=True,
                job_id=str(row[0]),
                payload=row[1],
                fencing_token=int(row[2]),
                lease_owner=row[3] or "",
            )

    def CompleteJob(self, request, context):
        with start_span(tracer, "grpc.complete"):
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO ledger_entries (job_id, fencing_token, account_id, delta)
                        VALUES (%s, %s, 'default', 1)
                        ON CONFLICT (job_id, fencing_token) DO NOTHING
                        """,
                        (request.job_id, int(request.fencing_token)),
                    )
                    cur.execute(
                        """
                        UPDATE jobs
                        SET state='succeeded',
                            lease_owner=NULL,
                            lease_expires_at=NULL,
                            next_run_at=NULL,
                            updated_at=NOW()
                        WHERE id=%s
                          AND state='running'
                          AND lease_owner=%s
                          AND fencing_token=%s
                          AND EXISTS (
                                SELECT 1 FROM ledger_entries
                                WHERE job_id=%s AND fencing_token=%s
                          )
                        RETURNING state
                        """,
                        (
                            request.job_id,
                            request.worker_id,
                            int(request.fencing_token),
                            request.job_id,
                            int(request.fencing_token),
                        ),
                    )
                    row = cur.fetchone()
                    conn.commit()
            return worker_pb2.CompleteJobResponse(ok=bool(row), state=(row[0] if row else "stale"))

    def GetJob(self, request, context):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, state, COALESCE(lease_owner, ''), fencing_token FROM jobs WHERE id=%s",
                    (request.job_id,),
                )
                row = cur.fetchone()
        if not row:
            context.abort(grpc.StatusCode.NOT_FOUND, "job not found")
        return worker_pb2.GetJobResponse(
            job_id=str(row[0]),
            state=row[1],
            lease_owner=row[2],
            fencing_token=int(row[3] or 0),
        )


def serve() -> None:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    worker_pb2_grpc.add_FaultlineWorkerServicer_to_server(FaultlineWorkerService(), server)
    server.add_insecure_port(f"[::]:{PORT}")
    server.start()
    print(f"faultline grpc listening on :{PORT}", flush=True)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()

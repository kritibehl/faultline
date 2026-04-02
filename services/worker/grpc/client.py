from __future__ import annotations

import os

import grpc

from services.worker.grpc import worker_pb2, worker_pb2_grpc  # type: ignore

TARGET = os.getenv("FAULTLINE_GRPC_TARGET", "localhost:50051")


def submit(payload: str = "{}") -> str:
    with grpc.insecure_channel(TARGET) as channel:
        stub = worker_pb2_grpc.FaultlineWorkerStub(channel)
        response = stub.SubmitJob(worker_pb2.SubmitJobRequest(payload=payload))
        print(f"submitted job_id={response.job_id} state={response.state}")
        return response.job_id


if __name__ == "__main__":
    submit()

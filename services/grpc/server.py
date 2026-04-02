from concurrent import futures
from pathlib import Path
import sys
import grpc

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import faultline_worker_pb2 as pb2
import faultline_worker_pb2_grpc as pb2_grpc

from common.observability.tracing import configure_tracing, get_tracer

configure_tracing()
tracer = get_tracer("faultline.grpc")

class FaultlineWorkerService(pb2_grpc.FaultlineWorkerServiceServicer):
    def ClaimJobs(self, request, context):
        with tracer.start_as_current_span("grpc.claim_jobs") as span:
            span.set_attribute("faultline.worker_id", request.worker_id)
            span.set_attribute("faultline.batch_size", request.batch_size)
            return pb2.ClaimResponse(jobs=[])

    def StartExecution(self, request, context):
        with tracer.start_as_current_span("grpc.start_execution") as span:
            span.set_attribute("faultline.job_id", request.job_id)
            span.set_attribute("faultline.fencing_token", request.fencing_token)
            return pb2.StartExecutionResponse(accepted=True, reason="ok")

    def CompleteExecution(self, request, context):
        with tracer.start_as_current_span("grpc.complete_execution") as span:
            span.set_attribute("faultline.job_id", request.job_id)
            span.set_attribute("faultline.fencing_token", request.fencing_token)
            return pb2.CompleteExecutionResponse(committed=True, reason="ok")

    def Heartbeat(self, request, context):
        with tracer.start_as_current_span("grpc.heartbeat") as span:
            span.set_attribute("faultline.job_id", request.job_id)
            span.set_attribute("faultline.fencing_token", request.fencing_token)
            return pb2.HeartbeatResponse(ok=True, lease_valid=True)

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    pb2_grpc.add_FaultlineWorkerServiceServicer_to_server(FaultlineWorkerService(), server)
    server.add_insecure_port("[::]:50051")
    server.start()
    print("Faultline gRPC server listening on :50051")
    server.wait_for_termination()

if __name__ == "__main__":
    serve()

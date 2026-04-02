import os
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

_SERVICE = os.getenv("OTEL_SERVICE_NAME", "faultline")

def configure_tracing() -> None:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": _SERVICE,
                "deployment.environment": os.getenv("FAULTLINE_ENV", "dev"),
            }
        )
    )
    exporter = OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

def get_tracer(name: str = "faultline"):
    return trace.get_tracer(name)

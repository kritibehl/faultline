from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from typing import Any

from opentelemetry import propagate, trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

_TRACING_INITIALIZED = False


def init_tracing(service_name: str) -> None:
    global _TRACING_INITIALIZED
    if _TRACING_INITIALIZED:
        return

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": service_name,
                "deployment.environment": os.getenv("FAULTLINE_ENV", "local"),
            }
        )
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True)))
    trace.set_tracer_provider(provider)
    _TRACING_INITIALIZED = True


def get_tracer(name: str):
    return trace.get_tracer(name)


def input_fingerprint(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def inject_traceparent(payload: dict[str, Any]) -> dict[str, Any]:
    carrier: dict[str, str] = {}
    TraceContextTextMapPropagator().inject(carrier)
    enriched = dict(payload)
    enriched["_traceparent"] = carrier.get("traceparent")
    if "tracestate" in carrier:
        enriched["_tracestate"] = carrier["tracestate"]
    return enriched


@contextmanager
def start_job_span_from_payload(tracer, span_name: str, payload: dict[str, Any] | None, **attrs):
    carrier = {}
    payload = payload or {}
    if "_traceparent" in payload:
        carrier["traceparent"] = payload["_traceparent"]
    if "_tracestate" in payload:
        carrier["tracestate"] = payload["_tracestate"]

    ctx = TraceContextTextMapPropagator().extract(carrier) if carrier else None

    if ctx:
        with tracer.start_as_current_span(span_name, context=ctx) as span:
            for k, v in attrs.items():
                span.set_attribute(k, v)
            yield span
    else:
        with tracer.start_as_current_span(span_name) as span:
            for k, v in attrs.items():
                span.set_attribute(k, v)
            yield span


@contextmanager
def start_span(tracer, span_name: str, **attrs):
    with tracer.start_as_current_span(span_name) as span:
        for k, v in attrs.items():
            span.set_attribute(k, v)
        yield span

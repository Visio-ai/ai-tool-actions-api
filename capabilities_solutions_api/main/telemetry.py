from __future__ import annotations

import os

from fastapi import FastAPI
from opentelemetry import propagate, trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from capabilities_solutions_api.main.settings import Settings

_provider_endpoint: str | None = None
_psycopg_instrumented = False


def resolve_otlp_endpoint(settings: Settings) -> str | None:
    return settings.otlp_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")


def configure_telemetry(app: FastAPI, settings: Settings) -> None:
    endpoint = resolve_otlp_endpoint(settings)
    if not endpoint:
        return

    _configure_provider(settings, endpoint)
    if not getattr(app.state, "otel_instrumented", False):
        FastAPIInstrumentor.instrument_app(app)
        app.state.otel_instrumented = True


def _configure_provider(settings: Settings, endpoint: str) -> None:
    global _provider_endpoint, _psycopg_instrumented

    if _provider_endpoint is None:
        propagate.set_global_textmap(CompositePropagator([TraceContextTextMapPropagator()]))
        resource = Resource.create(
            {"service.name": settings.otel_service_name or settings.app_name}
        )
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=settings.otlp_insecure)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _provider_endpoint = endpoint

    if not _psycopg_instrumented:
        PsycopgInstrumentor().instrument()
        _psycopg_instrumented = True

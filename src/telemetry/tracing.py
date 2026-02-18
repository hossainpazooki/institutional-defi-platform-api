"""OpenTelemetry distributed tracing configuration."""

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter


def setup_tracing(
    app: FastAPI,
    service_name: str = "institutional-defi-api",
    service_version: str = "0.1.0",
    enable_tracing: bool = True,
) -> None:
    """Configure OpenTelemetry tracing for FastAPI."""
    if not enable_tracing:
        return

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": service_version,
        }
    )

    provider = TracerProvider(resource=resource)
    processor = BatchSpanProcessor(ConsoleSpanExporter())
    provider.add_span_processor(processor)

    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls="health,metrics",
    )


def get_tracer(name: str) -> trace.Tracer:
    """Get an OpenTelemetry tracer."""
    return trace.get_tracer(name)


@contextmanager
def span(name: str, tracer_name: str = __name__) -> Iterator[trace.Span]:
    """Create a traced span context.

    Usage:
        with span("operation_name") as s:
            s.set_attribute("key", "value")
            # do work
    """
    tracer = get_tracer(tracer_name)
    with tracer.start_as_current_span(name) as s:
        yield s

"""Prometheus metrics definitions and FastAPI instrumentation helpers."""

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)
from starlette.requests import Request
from starlette.responses import Response

# HTTP metrics
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# Domain-specific metrics
RULE_EVALUATIONS = Counter(
    "rule_evaluations_total",
    "Total rule evaluations",
    ["jurisdiction", "result"],
)

DECODER_REQUESTS = Counter(
    "decoder_requests_total",
    "Total decoder requests",
    ["tier"],
)


async def metrics_endpoint(request: Request) -> Response:
    """Prometheus metrics endpoint handler. Mount at /metrics."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


def record_request_metrics(
    method: str,
    endpoint: str,
    status_code: int,
    duration: float,
) -> None:
    """Record HTTP request metrics."""
    REQUEST_COUNT.labels(
        method=method,
        endpoint=endpoint,
        status_code=str(status_code),
    ).inc()

    REQUEST_LATENCY.labels(
        method=method,
        endpoint=endpoint,
    ).observe(duration)

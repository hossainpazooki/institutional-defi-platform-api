"""Audit logging middleware and event models for request tracking.

Captures all API requests with timing, client info, and response status
for compliance audit trails.
"""

import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.telemetry.logging import bind_contextvars, clear_contextvars, get_logger

# Dedicated audit logger
audit_logger = get_logger("audit")


# ── Audit event models ──────────────────────────────────────────────


class AuditEventType(StrEnum):
    """Types of audit events."""

    REQUEST_START = "request_start"
    REQUEST_END = "request_end"
    AUTH_SUCCESS = "auth_success"
    AUTH_FAILURE = "auth_failure"
    RESOURCE_ACCESS = "resource_access"
    RESOURCE_CREATE = "resource_create"
    RESOURCE_UPDATE = "resource_update"
    RESOURCE_DELETE = "resource_delete"
    DECISION_MADE = "decision_made"
    RULE_EVALUATED = "rule_evaluated"
    ERROR = "error"


class AuditEvent(BaseModel):
    """Structured audit event for compliance logging."""

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: AuditEventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    request_id: str
    method: str
    path: str
    client_ip: str | None = None
    user_agent: str | None = None

    user_id: str | None = None
    api_key_id: str | None = None

    resource_type: str | None = None
    resource_id: str | None = None
    action: str | None = None

    status_code: int | None = None
    duration_ms: float | None = None

    details: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


def generate_request_id() -> str:
    """Generate a unique request ID for correlation."""
    return str(uuid.uuid4())


def log_audit_event(event: AuditEvent) -> None:
    """Log an audit event using structured logging."""
    audit_logger.info(
        "audit_event",
        event_id=event.event_id,
        event_type=event.event_type.value,
        timestamp=event.timestamp.isoformat(),
        request_id=event.request_id,
        method=event.method,
        path=event.path,
        client_ip=event.client_ip,
        user_agent=event.user_agent,
        user_id=event.user_id,
        api_key_id=event.api_key_id,
        resource_type=event.resource_type,
        resource_id=event.resource_id,
        action=event.action,
        status_code=event.status_code,
        duration_ms=event.duration_ms,
        details=event.details if event.details else None,
    )


def mask_api_key(api_key: str | None) -> str | None:
    """Mask an API key for safe logging."""
    if not api_key or len(api_key) < 12:
        return "****" if api_key else None
    return f"{api_key[:4]}...{api_key[-4:]}"


def extract_resource_info(path: str) -> tuple[str | None, str | None]:
    """Extract resource type and ID from request path."""
    clean_path = path.split("?")[0].strip("/")
    parts = clean_path.split("/")

    if not parts or not parts[0]:
        return None, None

    resource_type = parts[0]

    resource_id = None
    if len(parts) > 1:
        potential_id = parts[1]
        if potential_id.isdigit() or (len(potential_id) == 36 and potential_id.count("-") == 4):
            resource_id = potential_id

    return resource_type, resource_id


# ── Middleware ───────────────────────────────────────────────────────


class AuditMiddleware(BaseHTTPMiddleware):
    """Middleware that logs all requests for audit purposes."""

    EXCLUDED_PATHS: set[str] = {
        "/health",
        "/metrics",
        "/favicon.ico",
        "/openapi.json",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
    }

    def __init__(
        self,
        app: Callable,
        enabled: bool = True,
        sensitive_paths: list[str] | None = None,
    ) -> None:
        super().__init__(app)
        self.enabled = enabled
        self.sensitive_paths = sensitive_paths or ["/decide", "/rules", "/ke"]

    def _should_audit(self, path: str) -> bool:
        if not self.enabled:
            return False
        return path not in self.EXCLUDED_PATHS

    def _is_sensitive(self, path: str) -> bool:
        return any(path.startswith(p) for p in self.sensitive_paths)

    def _get_client_ip(self, request: Request) -> str | None:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return None

    def _get_api_key_id(self, request: Request) -> str | None:
        api_key = request.headers.get("x-api-key")
        return mask_api_key(api_key)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        if not self._should_audit(path):
            return await call_next(request)

        request_id = generate_request_id()
        bind_contextvars(request_id=request_id)
        request.state.request_id = request_id

        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent")
        api_key_id = self._get_api_key_id(request)
        resource_type, resource_id = extract_resource_info(path)

        if self._is_sensitive(path):
            start_event = AuditEvent(
                event_type=AuditEventType.REQUEST_START,
                request_id=request_id,
                method=request.method,
                path=path,
                client_ip=client_ip,
                user_agent=user_agent,
                api_key_id=api_key_id,
                resource_type=resource_type,
                resource_id=resource_id,
            )
            log_audit_event(start_event)

        start_time = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start_time) * 1000
            error_event = AuditEvent(
                event_type=AuditEventType.ERROR,
                request_id=request_id,
                method=request.method,
                path=path,
                client_ip=client_ip,
                user_agent=user_agent,
                api_key_id=api_key_id,
                resource_type=resource_type,
                resource_id=resource_id,
                duration_ms=round(duration_ms, 2),
                details={"error": "Unhandled exception"},
            )
            log_audit_event(error_event)
            clear_contextvars()
            raise

        duration_ms = (time.perf_counter() - start_time) * 1000

        end_event = AuditEvent(
            event_type=AuditEventType.REQUEST_END,
            request_id=request_id,
            method=request.method,
            path=path,
            client_ip=client_ip,
            user_agent=user_agent,
            api_key_id=api_key_id,
            resource_type=resource_type,
            resource_id=resource_id,
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
        )
        log_audit_event(end_event)

        response.headers["X-Request-ID"] = request_id
        clear_contextvars()

        return response

"""Security headers middleware for FastAPI.

Adds standard security headers to all responses to protect against common
web vulnerabilities like clickjacking, XSS, and MIME-type sniffing.
"""

from collections.abc import Callable
from typing import Any, cast

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware that adds security headers to all responses."""

    def __init__(
        self,
        app: Callable[..., Any],
        csp_policy: str | None = None,
        include_csp: bool = True,
    ) -> None:
        super().__init__(app)
        self.include_csp = include_csp
        self.csp_policy = csp_policy or self._default_csp()

    @staticmethod
    def _default_csp() -> str:
        return "; ".join(
            [
                "default-src 'self'",
                "script-src 'self'",
                "style-src 'self' 'unsafe-inline'",
                "img-src 'self' data:",
                "font-src 'self'",
                "frame-ancestors 'none'",
                "base-uri 'self'",
                "form-action 'self'",
            ]
        )

    async def dispatch(self, request: Request, call_next: Callable[..., Any]) -> Response:
        response = cast("Response", await call_next(request))

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        response.headers["Permissions-Policy"] = (
            "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
            "magnetometer=(), microphone=(), payment=(), usb=()"
        )

        if self.include_csp:
            response.headers["Content-Security-Policy"] = self.csp_policy

        return response

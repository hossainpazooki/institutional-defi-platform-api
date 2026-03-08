"""API key authentication for FastAPI.

Provides optional API key authentication that can be enabled via environment
variables. When disabled, all requests are allowed through.
"""

from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from src.config import get_settings

API_KEY_HEADER = "X-API-Key"

api_key_header_scheme = APIKeyHeader(name=API_KEY_HEADER, auto_error=False)


def get_valid_api_keys() -> set[str]:
    """Get the set of valid API keys from settings."""
    settings = get_settings()
    if not settings.api_keys:
        return set()
    return {key.strip() for key in settings.api_keys.split(",") if key.strip()}


async def verify_api_key(
    api_key: str | None = Depends(api_key_header_scheme),
) -> str | None:
    """Verify the API key if authentication is required."""
    settings = get_settings()

    if not settings.require_auth:
        return None

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Include 'X-API-Key' header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    valid_keys = get_valid_api_keys()
    if not valid_keys:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication required but no API keys configured.",
        )

    if api_key not in valid_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return api_key


def get_api_key_header() -> Any:
    """Dependency for endpoints requiring API key authentication."""
    return Depends(verify_api_key)


class OptionalAuthMiddleware:
    """Middleware for global API key verification.

    Checks API key on all requests when REQUIRE_AUTH=true.
    Skips auth for health/metrics endpoints.
    """

    SKIP_PATHS = {"/health", "/metrics", "/", "/docs", "/redoc", "/openapi.json"}

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        path = request.url.path

        if path in self.SKIP_PATHS:
            await self.app(scope, receive, send)
            return

        settings = get_settings()
        if not settings.require_auth:
            await self.app(scope, receive, send)
            return

        api_key = request.headers.get(API_KEY_HEADER)
        valid_keys = get_valid_api_keys()

        if not valid_keys:
            response = JSONResponse(
                status_code=500,
                content={"detail": "Authentication required but no API keys configured."},
            )
            await response(scope, receive, send)
            return

        if not api_key or api_key not in valid_keys:
            response = JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key."},
                headers={"WWW-Authenticate": "ApiKey"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)

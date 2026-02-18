"""Observability service — tracing, metrics, and structured logging."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.telemetry.logging import configure_logging, get_logger

if TYPE_CHECKING:
    from fastapi import FastAPI


def setup_telemetry(app: FastAPI) -> None:
    """Initialize all telemetry subsystems. Called from main.py lifespan."""
    from src.config import get_settings

    settings = get_settings()

    # Structured logging
    configure_logging(
        log_level=settings.log_level,
        log_format=settings.log_format,
    )

    # Distributed tracing (optional)
    if settings.enable_tracing:
        from src.telemetry.tracing import setup_tracing

        setup_tracing(
            app,
            service_name=settings.service_name,
            enable_tracing=True,
        )

    logger = get_logger("telemetry")
    logger.info(
        "telemetry_initialized",
        tracing=settings.enable_tracing,
        log_level=settings.log_level,
    )


__all__ = ["configure_logging", "get_logger", "setup_telemetry"]

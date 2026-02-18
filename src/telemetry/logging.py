"""Structured logging configuration using structlog.

Provides JSON-formatted logs for production and human-readable console
output for development. Configured via LOG_LEVEL and LOG_FORMAT env vars.
"""

import logging
import sys
from typing import TYPE_CHECKING, Literal

import structlog

if TYPE_CHECKING:
    from structlog.types import Processor


def configure_logging(
    log_level: str = "INFO",
    log_format: Literal["json", "console"] = "json",
) -> None:
    """Configure structured logging for the application.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Output format - "json" for production, "console" for dev
    """
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if log_format == "json":
        processors: list[Processor] = [
            *shared_processors,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        processors = [
            *shared_processors,
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, log_level.upper())),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


# Convenience re-exports
bind_contextvars = structlog.contextvars.bind_contextvars
clear_contextvars = structlog.contextvars.clear_contextvars

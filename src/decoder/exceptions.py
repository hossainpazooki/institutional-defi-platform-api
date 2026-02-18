"""Decoder-specific exceptions."""

from __future__ import annotations

from src.exceptions import AppException


class DecoderServiceError(AppException):
    """Raised when the decoder service encounters an error."""

"""Configuration for the decoder domain."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class DecoderConfig(BaseSettings):
    """Decoder-specific configuration."""

    anthropic_api_key: str | None = None

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

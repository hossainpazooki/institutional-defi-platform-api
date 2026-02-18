"""Telemetry configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class TelemetryConfig(BaseSettings):
    """Telemetry-specific settings, loaded from environment."""

    enable_tracing: bool = False
    enable_metrics: bool = True
    otel_exporter_endpoint: str = "http://localhost:4317"
    service_name: str = "institutional-defi-api"
    service_version: str = "0.1.0"
    log_level: str = "INFO"
    log_format: str = "json"  # "json" or "console"

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

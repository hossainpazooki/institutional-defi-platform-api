"""Workflow configuration settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkflowConfig(BaseSettings):
    """Configuration for Temporal workflow integration."""

    model_config = SettingsConfigDict(env_prefix="TEMPORAL_", extra="ignore")

    host: str = "localhost:7233"
    namespace: str = "default"
    task_queue: str = "compliance-workflows"

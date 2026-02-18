"""RAG domain configuration."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class RAGConfig(BaseSettings):
    """RAG-specific settings loaded from environment variables."""

    enable_vector_search: bool = False
    openai_api_key: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

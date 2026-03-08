"""Global configuration settings for Institutional DeFi Platform API.

Merges settings from:
- applied-ai-regulatory-workbench (Workbench): logging, telemetry, security, audit, ML flags
- crypto-portfolio-risk-console (Console): database, Redis, blockchain RPCs, LLM, feature flags

Domain-specific settings live in src/{domain}/config.py.
"""

from functools import lru_cache
from typing import Any, Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ── Application ──────────────────────────────────────────────────────
    app_name: str = "Institutional DeFi Platform API"
    environment: str = "local"  # local, staging, production
    debug: bool = False

    # ── Database (PostgreSQL + TimescaleDB) ──────────────────────────────
    database_url: str = "postgresql://postgres:postgres@localhost:5432/institutional_defi"

    # ── Redis ────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Logging ──────────────────────────────────────────────────────────
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"

    # ── Security / Auth ──────────────────────────────────────────────────
    require_auth: bool = False
    api_keys: str | None = None  # Comma-separated valid API keys
    enable_rate_limiting: bool = True
    rate_limit_default: str = "100/minute"

    # ── Audit ────────────────────────────────────────────────────────────
    enable_audit_logging: bool = True
    audit_sensitive_paths: str = "/decide,/rules,/ke"

    # ── Telemetry ────────────────────────────────────────────────────────
    enable_tracing: bool = True
    service_name: str = "institutional-defi-api"

    # ── Blockchain RPC URLs (Console) ────────────────────────────────────
    ethereum_rpc_url: str | None = None
    base_rpc_url: str | None = None
    polygon_rpc_url: str | None = None
    solana_rpc_url: str | None = None
    arbitrum_rpc_url: str | None = None
    avalanche_rpc_url: str | None = None

    # ── LLM (Anthropic) ─────────────────────────────────────────────────
    anthropic_api_key: str | None = None

    # ── Feature flags ────────────────────────────────────────────────────
    enable_feature_store: bool = True
    enable_decoder_service: bool = True
    enable_jpm_scenarios: bool = True
    enable_vector_search: bool = False
    openai_api_key: str | None = None

    # ── Credit Pipeline ────────────────────────────────────────────────
    pydanticai_model: str = "claude-sonnet-4-20250514"
    enable_credit_pipeline: bool = True

    # ── Paths ────────────────────────────────────────────────────────────
    rules_dir: str = "src/rules/data"
    data_dir: str = "data"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def ml_available() -> bool:
    """Check if ML dependencies (sentence-transformers, chromadb) are installed."""
    try:
        import chromadb  # noqa: F401
        import sentence_transformers  # noqa: F401

        return True
    except ImportError:
        return False


_sentence_transformer: Any = None
_sentence_transformer_checked: bool = False

SENTENCE_TRANSFORMER_MODEL = "all-MiniLM-L6-v2"


def get_sentence_transformer() -> Any:
    """Get or create a shared SentenceTransformer instance.

    Returns the cached model, or None if sentence-transformers is not installed.
    """
    global _sentence_transformer, _sentence_transformer_checked
    if not _sentence_transformer_checked:
        try:
            from sentence_transformers import SentenceTransformer

            _sentence_transformer = SentenceTransformer(SENTENCE_TRANSFORMER_MODEL)
        except ImportError:
            _sentence_transformer = None
        _sentence_transformer_checked = True
    return _sentence_transformer

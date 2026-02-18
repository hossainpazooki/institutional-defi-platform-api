"""Feature Store domain configuration."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class FeatureStoreConfig(BaseSettings):
    """Configuration for the Feature Store."""

    model_config = SettingsConfigDict(env_prefix="FEATURE_STORE_", extra="ignore")

    enable_feature_store: bool = True
    default_window: str = "30d"
    max_points_per_query: int = 10_000

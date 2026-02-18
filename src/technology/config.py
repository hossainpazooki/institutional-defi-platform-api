"""Technology domain configuration."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class TechnologyConfig(BaseSettings):
    """Configuration for chain/RPC monitoring."""

    model_config = SettingsConfigDict(env_prefix="TECH_", extra="ignore")

    ethereum_rpc_url: str = ""
    base_rpc_url: str = ""
    polygon_rpc_url: str = ""
    solana_rpc_url: str = ""
    check_interval_seconds: int = 30

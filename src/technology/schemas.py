"""Pydantic schemas for Technology domain."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ChainStatus(BaseModel):
    """Status of a blockchain network."""

    chain_id: str
    name: str
    status: str  # "healthy", "degraded", "down"
    latest_block: int
    block_time_ms: float
    tps: float
    gas_price_gwei: float | None = None
    validator_count: int | None = None
    last_checked: datetime


class ChainsResponse(BaseModel):
    """Response model for chains status endpoint."""

    chains: list[ChainStatus]
    as_of: datetime


class RPCEndpoint(BaseModel):
    """RPC endpoint health status."""

    chain_id: str
    provider: str
    url: str
    latency_ms: float
    status: str  # "healthy", "degraded", "down"
    last_error: str | None = None


class RPCHealthResponse(BaseModel):
    """Response model for RPC health endpoint."""

    endpoints: list[RPCEndpoint]
    as_of: datetime


class ContractInfo(BaseModel):
    """Smart contract information."""

    address: str
    chain_id: str
    name: str
    verified: bool
    audit_status: str | None = None
    deployed_at: datetime | None = None

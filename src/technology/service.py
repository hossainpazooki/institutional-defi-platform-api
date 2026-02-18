"""Technology domain service — chain and RPC monitoring."""

from __future__ import annotations

from datetime import UTC, datetime

from src.technology.schemas import (
    ChainsResponse,
    ChainStatus,
    RPCEndpoint,
    RPCHealthResponse,
)


class TechnologyService:
    """Business logic for chain/RPC monitoring."""

    async def get_chains_status(self) -> ChainsResponse:
        """Get status of all monitored blockchain networks."""
        now = datetime.now(tz=UTC)
        return ChainsResponse(
            chains=[
                ChainStatus(
                    chain_id="ethereum",
                    name="Ethereum",
                    status="healthy",
                    latest_block=19_500_000,
                    block_time_ms=12000,
                    tps=15.5,
                    gas_price_gwei=25.0,
                    validator_count=900_000,
                    last_checked=now,
                ),
                ChainStatus(
                    chain_id="base",
                    name="Base",
                    status="healthy",
                    latest_block=10_000_000,
                    block_time_ms=2000,
                    tps=45.0,
                    gas_price_gwei=0.001,
                    last_checked=now,
                ),
                ChainStatus(
                    chain_id="polygon",
                    name="Polygon",
                    status="healthy",
                    latest_block=55_000_000,
                    block_time_ms=2000,
                    tps=35.0,
                    gas_price_gwei=50.0,
                    validator_count=100,
                    last_checked=now,
                ),
                ChainStatus(
                    chain_id="solana",
                    name="Solana",
                    status="healthy",
                    latest_block=250_000_000,
                    block_time_ms=400,
                    tps=4000.0,
                    validator_count=1900,
                    last_checked=now,
                ),
            ],
            as_of=now,
        )

    async def get_rpc_health(self) -> RPCHealthResponse:
        """Get RPC endpoint health status."""
        now = datetime.now(tz=UTC)
        return RPCHealthResponse(
            endpoints=[
                RPCEndpoint(
                    chain_id="ethereum",
                    provider="alchemy",
                    url="https://eth-mainnet.g.alchemy.com/v2/***",
                    latency_ms=45.0,
                    status="healthy",
                ),
                RPCEndpoint(
                    chain_id="base",
                    provider="alchemy",
                    url="https://base-mainnet.g.alchemy.com/v2/***",
                    latency_ms=38.0,
                    status="healthy",
                ),
                RPCEndpoint(
                    chain_id="solana",
                    provider="helius",
                    url="https://mainnet.helius-rpc.com/***",
                    latency_ms=55.0,
                    status="healthy",
                ),
            ],
            as_of=now,
        )

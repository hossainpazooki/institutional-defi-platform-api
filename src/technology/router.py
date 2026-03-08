"""Technology domain API endpoints — chain and RPC monitoring."""

from __future__ import annotations

from fastapi import APIRouter

from src.technology.schemas import ChainsResponse, RPCHealthResponse
from src.technology.service import TechnologyService

router = APIRouter()

_service = TechnologyService()


@router.get("/chains", response_model=ChainsResponse)
async def get_chains_status() -> ChainsResponse:
    """Get status of all monitored blockchain networks."""
    return await _service.get_chains_status()


@router.get("/rpc", response_model=RPCHealthResponse)
async def get_rpc_health() -> RPCHealthResponse:
    """Get RPC endpoint health status."""
    return await _service.get_rpc_health()


@router.get("/contracts")
async def get_contracts() -> dict[str, str]:
    """Get monitored smart contracts."""
    return {"status": "stub", "module": "technology.contracts"}


@router.get("/alerts")
async def get_tech_alerts() -> dict[str, str]:
    """Get technology alerts."""
    return {"status": "stub", "module": "technology.alerts"}


@router.get("/metrics")
async def get_tech_metrics() -> dict[str, str]:
    """Get technology performance metrics."""
    return {"status": "stub", "module": "technology.metrics"}

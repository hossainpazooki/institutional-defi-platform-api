"""DeFi risk API routes — unified /defi-risk/* (Workbench) + /research/* (Console) endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from . import service
from .schemas import (
    DeFiCategory,
    DeFiRiskScore,
    DeFiScoreRequest,
    EconomicRisk,
    GovernanceRisk,
    OracleRisk,
    ProtocolsResponse,
    SmartContractRisk,
    TokenomicsResponse,
)
from .service import DeFiResearchService

defi_risk_router = APIRouter(prefix="/defi-risk", tags=["DeFi Risk"])
research_router = APIRouter(prefix="/research", tags=["DeFi Risk"])

_research_service = DeFiResearchService()


# =============================================================================
# /defi-risk/* endpoints (from Workbench)
# =============================================================================


@defi_risk_router.post("/score", response_model=DeFiRiskScore)
async def score_protocol(request: DeFiScoreRequest) -> DeFiRiskScore:
    """Score a DeFi protocol across risk dimensions."""
    return service.score_defi_protocol(
        protocol_id=request.protocol_id,
        category=request.category,
        smart_contract=request.smart_contract,
        economic=request.economic,
        oracle=request.oracle,
        governance=request.governance,
    )


@defi_risk_router.get("/protocols")
async def list_protocol_defaults() -> dict[str, list[str]]:
    """List available protocol default configurations."""
    return {"protocols": service.list_protocol_defaults()}


@defi_risk_router.get("/protocols/{protocol_id}")
async def get_protocol_config(protocol_id: str) -> dict[str, Any]:
    """Get default configuration for a known protocol."""
    config = service.get_protocol_defaults(protocol_id)
    if not config:
        raise HTTPException(
            status_code=404,
            detail=f"Protocol '{protocol_id}' not found. Available: {service.list_protocol_defaults()}",
        )
    return {"protocol_id": protocol_id, **config}


@defi_risk_router.post("/protocols/{protocol_id}/score", response_model=DeFiRiskScore)
async def score_known_protocol(protocol_id: str) -> DeFiRiskScore:
    """Score a known protocol using its default configuration."""
    config = service.get_protocol_defaults(protocol_id)
    if not config:
        raise HTTPException(
            status_code=404,
            detail=f"Protocol '{protocol_id}' not found. Available: {service.list_protocol_defaults()}",
        )
    return service.score_defi_protocol(
        protocol_id=protocol_id,
        category=config["category"],
        smart_contract=SmartContractRisk(**config.get("smart_contract", {})),
        economic=EconomicRisk(**config.get("economic", {})),
        oracle=OracleRisk(**config.get("oracle", {})),
        governance=GovernanceRisk(**config.get("governance", {})),
    )


@defi_risk_router.get("/categories")
async def list_categories() -> dict[str, list[str]]:
    """List DeFi protocol categories."""
    return {"categories": [c.value for c in DeFiCategory]}


# =============================================================================
# /research/* endpoints (from Console)
# =============================================================================


@research_router.get("/protocols", response_model=ProtocolsResponse)
async def get_protocols() -> ProtocolsResponse:
    """Get DeFi protocol information and risk grades."""
    return await _research_service.get_protocols()


@research_router.get("/tokenomics", response_model=TokenomicsResponse)
async def get_tokenomics() -> TokenomicsResponse:
    """Get token economics data."""
    return await _research_service.get_tokenomics()


@research_router.get("/trends")
async def get_trends() -> dict[str, str]:
    """Get market trends analysis."""
    return {"status": "stub", "module": "research.trends"}


@research_router.get("/governance")
async def get_governance() -> dict[str, str]:
    """Get protocol governance updates."""
    return {"status": "stub", "module": "research.governance"}

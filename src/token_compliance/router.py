"""Token compliance analysis API endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from src.token_compliance import service
from src.token_compliance.schemas import (
    GeniusActAnalysis,
    GeniusActRequest,
    HoweyTestRequest,
    HoweyTestResult,
    TokenComplianceRequest,
    TokenComplianceResult,
)

router = APIRouter()


@router.post("/howey-test", response_model=HoweyTestResult)
async def apply_howey_test(request: HoweyTestRequest) -> HoweyTestResult:
    """Apply SEC Howey Test to determine security classification."""
    return service.apply_howey_test(
        investment_of_money=request.investment_of_money,
        common_enterprise=request.common_enterprise,
        expectation_of_profits=request.expectation_of_profits,
        efforts_of_others=request.efforts_of_others,
        decentralization_score=request.decentralization_score,
        is_functional_network=request.is_functional_network,
    )


@router.post("/genius-act", response_model=GeniusActAnalysis)
async def analyze_genius_act(request: GeniusActRequest) -> GeniusActAnalysis:
    """Analyze compliance with GENIUS Act stablecoin provisions."""
    return service.analyze_genius_act_compliance(
        is_stablecoin=request.is_stablecoin,
        pegged_currency=request.pegged_currency,
        reserve_assets=request.reserve_assets,
        reserve_ratio=request.reserve_ratio,
        uses_algorithmic_mechanism=request.uses_algorithmic_mechanism,
        issuer_charter_type=request.issuer_charter_type,
        has_reserve_attestation=request.has_reserve_attestation,
        attestation_frequency_days=request.attestation_frequency_days,
    )


@router.post("/analyze", response_model=TokenComplianceResult)
async def analyze_token_compliance(request: TokenComplianceRequest) -> TokenComplianceResult:
    """Comprehensive token compliance analysis."""
    return service.analyze_token_compliance(**request.model_dump())


@router.get("/standards")
async def list_token_standards() -> dict:
    """List supported token standards."""
    return {"standards": service.list_token_standards()}

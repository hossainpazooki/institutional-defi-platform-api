"""JPM Scenarios API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from src.jpm_scenarios.schemas import (
    MemoResponse,
    ScenarioRunResult,
    ScenariosResponse,
)
from src.jpm_scenarios.service import JPMScenarioService

router = APIRouter(prefix="/jpm", tags=["JPM Scenarios"])

_service: JPMScenarioService | None = None


def _get_service() -> JPMScenarioService:
    global _service
    if _service is None:
        _service = JPMScenarioService()
    return _service


@router.get("/scenarios", response_model=ScenariosResponse)
async def list_scenarios() -> ScenariosResponse:
    """List all available JPM tokenization scenarios.

    Returns pre-configured scenarios for institutional tokenization use cases.
    """
    return _get_service().list_scenarios()


@router.get("/scenarios/{scenario_id}")
async def get_scenario(scenario_id: str) -> dict[str, Any]:
    """Get details of a specific scenario."""
    result = _get_service().get_scenario(scenario_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Scenario not found: {scenario_id}")
    return dict(result)


@router.post("/scenarios/{scenario_id}/run", response_model=ScenarioRunResult)
async def run_scenario(scenario_id: str) -> ScenarioRunResult:
    """Execute a JPM scenario through the full risk pipeline.

    Steps:
    1. Protocol/chain risk assessment
    2. DeFi protocol risk (if applicable)
    3. Market risk assessment
    4. Compliance/regulatory pathway
    5. Decoder explanation

    Note: This is a stub implementation returning mock data.
    """
    result = _get_service().run_scenario(scenario_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Scenario not found: {scenario_id}")
    return result


@router.post("/scenarios/{scenario_id}/memo", response_model=MemoResponse)
async def generate_memo(
    scenario_id: str,
    format: str = Query("markdown", pattern="^(markdown|pdf)$"),
) -> MemoResponse:
    """Generate an audit-ready memo for a scenario.

    Supported formats:
    - markdown: Returns markdown content
    - pdf: Returns base64-encoded PDF (stub returns placeholder)
    """
    result = _get_service().generate_memo(scenario_id, fmt=format)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Scenario not found: {scenario_id}")
    return result

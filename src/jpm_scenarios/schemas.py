"""Pydantic schemas for JPM Scenarios domain."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.models import CustomBaseModel


class ScenarioSummary(CustomBaseModel):
    """Summary information for a JPM scenario."""

    id: str
    name: str
    description: str
    chain: str
    instrument_type: str
    jurisdictions: list[str]
    defi_protocols: list[str]


class ScenariosResponse(CustomBaseModel):
    """Response model for listing scenarios."""

    scenarios: list[ScenarioSummary]
    count: int


class ProtocolRiskResult(CustomBaseModel):
    """Protocol/chain risk assessment result."""

    chain_id: str
    profile: dict
    recommendations: list[str]
    computed_at: datetime


class MarketRiskResult(CustomBaseModel):
    """Market risk assessment result."""

    var_99: float
    var_99_10d: float
    cvar_99: float
    exposure_usd: float
    volatility_30d: float


class ComplianceResult(CustomBaseModel):
    """Compliance pathway result."""

    status: str  # "approved", "conditional", "blocked"
    jurisdictions: list[str]
    conflicts: list[str]
    requirements: list[str]


class ExplanationResult(CustomBaseModel):
    """Decoder explanation result."""

    decision: str
    confidence: float
    explanation: str
    citations: list[dict]
    tier: str


class ScenarioRunResult(CustomBaseModel):
    """Full result of running a JPM scenario."""

    scenario_id: str
    scenario_name: str
    timestamp: datetime
    results: dict[str, Any]
    explanation: ExplanationResult | None = None
    recommendations: list[str]
    overall_risk_score: float


class MemoRequest(CustomBaseModel):
    """Request model for memo generation."""

    format: str = "markdown"  # "markdown" or "pdf"


class MemoResponse(CustomBaseModel):
    """Response model for memo generation."""

    scenario_id: str
    scenario_name: str
    format: str
    content: str  # Markdown content or base64 PDF
    generated_at: datetime

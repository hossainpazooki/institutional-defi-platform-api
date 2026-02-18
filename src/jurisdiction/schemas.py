"""Unified jurisdiction schemas.

Combines:
- Workbench routes_navigate.py: NavigateRequest, NavigateResponse, JurisdictionRoleResponse
- Console compliance/schemas.py: JurisdictionInfo, SanctionsResponse, ComplianceAlert
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from src.models import CustomBaseModel

# =============================================================================
# Navigate Schemas (from Workbench routes_navigate.py)
# =============================================================================


class NavigateRequest(CustomBaseModel):
    """Cross-border compliance navigation request (v4 spec)."""

    issuer_jurisdiction: str = Field(
        ...,
        description="Jurisdiction code where the issuer is based",
        examples=["CH", "EU", "UK"],
    )
    target_jurisdictions: list[str] = Field(
        default_factory=list,
        description="Target market jurisdiction codes",
        examples=[["EU", "UK"]],
    )
    instrument_type: str = Field(
        ...,
        description="Type of digital asset/instrument",
        examples=["stablecoin", "tokenized_bond", "crypto_asset"],
    )
    activity: str = Field(
        ...,
        description="Regulatory activity being performed",
        examples=["public_offer", "financial_promotion", "custody"],
    )
    investor_types: list[str] = Field(
        default=["professional"],
        description="Types of investors targeted",
        examples=[["retail", "professional"]],
    )
    facts: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional facts for rule evaluation",
    )
    token_standard: str | None = Field(
        None,
        description="Token standard (ERC-20, BEP-20, SPL, etc.)",
        examples=["ERC-20", "BEP-20", "SPL"],
    )
    underlying_chain: str | None = Field(
        None,
        description="Underlying blockchain protocol",
        examples=["ethereum", "solana", "polygon", "avalanche"],
    )
    is_defi_integrated: bool = Field(
        False,
        description="Whether the instrument integrates with DeFi protocols",
    )
    defi_protocol: str | None = Field(
        None,
        description="DeFi protocol name if integrated",
        examples=["aave_v3", "uniswap_v3", "lido", "gmx"],
    )


class JurisdictionRoleResponse(CustomBaseModel):
    """Jurisdiction with role in cross-border scenario."""

    jurisdiction: str
    regime_id: str
    role: str


class NavigateResponse(CustomBaseModel):
    """Cross-border compliance navigation result (v4 spec)."""

    status: str = Field(
        ...,
        description="Overall status: actionable, blocked, requires_review",
    )
    applicable_jurisdictions: list[JurisdictionRoleResponse]
    jurisdiction_results: list[dict]
    conflicts: list[dict]
    pathway: list[dict]
    cumulative_obligations: list[dict]
    estimated_timeline: str
    audit_trail: list[dict]
    token_compliance: dict | None = Field(
        None,
        description="Token standard compliance analysis (Howey test, GENIUS Act)",
    )
    protocol_risk: dict | None = Field(
        None,
        description="Underlying blockchain protocol risk assessment",
    )
    defi_risk: dict | None = Field(
        None,
        description="DeFi protocol risk score if integrated",
    )


# =============================================================================
# Compliance Schemas (from Console compliance/schemas.py)
# =============================================================================


class JurisdictionInfo(CustomBaseModel):
    """Jurisdiction regulatory information."""

    jurisdiction_code: str
    name: str
    regulatory_status: str  # "clear", "developing", "restricted", "prohibited"
    crypto_classification: str  # "commodity", "security", "currency", "other"
    key_requirements: list[str]
    last_updated: datetime


class JurisdictionsResponse(CustomBaseModel):
    """Response model for jurisdictions endpoint."""

    jurisdictions: list[JurisdictionInfo]
    as_of: datetime


class SanctionCheckResult(CustomBaseModel):
    """Sanction screening result."""

    address: str
    chain: str
    is_sanctioned: bool
    sanction_lists: list[str]
    risk_score: float
    checked_at: datetime


class SanctionsResponse(CustomBaseModel):
    """Response model for sanctions check endpoint."""

    results: list[SanctionCheckResult]
    total_checked: int
    flagged_count: int
    as_of: datetime


class ComplianceAlert(CustomBaseModel):
    """Compliance alert."""

    alert_id: str
    severity: str  # "low", "medium", "high", "critical"
    category: str
    message: str
    entity_id: str | None = None
    created_at: datetime
    acknowledged: bool = False

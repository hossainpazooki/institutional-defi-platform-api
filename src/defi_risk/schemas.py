"""Unified DeFi risk schemas — protocol scoring, research, tokenomics."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums (from Workbench defi_risk)
# ---------------------------------------------------------------------------


class DeFiCategory(StrEnum):
    """DeFi protocol categories."""

    STAKING = "staking"
    LIQUIDITY_POOL = "liquidity_pool"
    LENDING = "lending"
    BRIDGE = "bridge"
    DEX = "dex"
    YIELD_AGGREGATOR = "yield_aggregator"
    DERIVATIVES = "derivatives"
    STABLECOIN = "stablecoin"
    INSURANCE = "insurance"
    RESTAKING = "restaking"


class GovernanceType(StrEnum):
    """Governance mechanism types."""

    TOKEN_VOTING = "token_voting"
    MULTISIG = "multisig"
    OPTIMISTIC = "optimistic"
    IMMUTABLE = "immutable"
    CENTRALIZED = "centralized"
    HYBRID = "hybrid"


class OracleProvider(StrEnum):
    """Oracle service providers."""

    CHAINLINK = "chainlink"
    PYTH = "pyth"
    BAND = "band"
    UNISWAP_TWAP = "uniswap_twap"
    CUSTOM = "custom"
    NONE = "none"


class RiskGrade(StrEnum):
    """Letter grade risk rating (A=lowest risk, F=highest risk)."""

    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"


# ---------------------------------------------------------------------------
# Risk dimension inputs (from Workbench)
# ---------------------------------------------------------------------------


class SmartContractRisk(BaseModel):
    """Smart contract risk assessment inputs."""

    audit_count: int = Field(0, ge=0)
    auditors: list[str] = Field(default_factory=list)
    last_audit_days_ago: int = Field(365, ge=0)
    formal_verification: bool = False
    is_upgradeable: bool = True
    upgrade_timelock_hours: int = Field(0, ge=0)
    has_admin_functions: bool = True
    admin_can_pause: bool = True
    admin_can_drain: bool = False
    tvl_usd: float = Field(0, ge=0)
    contract_age_days: int = Field(0, ge=0)
    exploit_history_count: int = Field(0, ge=0)
    total_exploit_loss_usd: float = Field(0, ge=0)
    bug_bounty_max_usd: float = Field(0, ge=0)


class EconomicRisk(BaseModel):
    """Economic and tokenomics risk assessment."""

    token_concentration_top10_pct: float = Field(50.0, ge=0, le=100)
    team_token_pct: float = Field(20.0, ge=0, le=100)
    vesting_remaining_pct: float = Field(50.0, ge=0, le=100)
    treasury_runway_months: float = Field(24.0, ge=0)
    treasury_diversified: bool = False
    has_protocol_revenue: bool = True
    revenue_30d_usd: float = Field(0, ge=0)
    has_impermanent_loss: bool = False
    has_liquidation_risk: bool = False
    max_leverage: float = Field(1.0, ge=1.0)


class OracleRisk(BaseModel):
    """Oracle dependency risk assessment."""

    primary_oracle: OracleProvider = OracleProvider.CHAINLINK
    has_fallback_oracle: bool = False
    oracle_update_frequency_seconds: int = Field(3600, ge=1)
    oracle_manipulation_resistant: bool = True
    oracle_decentralized: bool = True
    oracle_failure_count_12m: int = Field(0, ge=0)
    oracle_deviation_threshold_pct: float = Field(1.0, gt=0)


class GovernanceRisk(BaseModel):
    """Governance and centralization risk assessment."""

    governance_type: GovernanceType = GovernanceType.TOKEN_VOTING
    has_timelock: bool = True
    timelock_hours: int = Field(48, ge=0)
    multisig_threshold: str | None = None
    multisig_signers_doxxed: bool = False
    governance_participation_pct: float = Field(10.0, ge=0, le=100)
    quorum_pct: float = Field(4.0, ge=0, le=100)
    has_emergency_admin: bool = True
    emergency_actions_12m: int = Field(0, ge=0)


# ---------------------------------------------------------------------------
# DeFi risk score output (from Workbench)
# ---------------------------------------------------------------------------


class DeFiRiskScore(BaseModel):
    """Comprehensive DeFi protocol risk score."""

    protocol_id: str
    category: DeFiCategory
    smart_contract_grade: RiskGrade
    economic_grade: RiskGrade
    oracle_grade: RiskGrade
    governance_grade: RiskGrade
    overall_grade: RiskGrade
    overall_score: float = Field(..., ge=0, le=100)
    smart_contract_score: float
    economic_score: float
    oracle_score: float
    governance_score: float
    critical_risks: list[str] = Field(default_factory=list)
    high_risks: list[str] = Field(default_factory=list)
    medium_risks: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    regulatory_flags: list[str] = Field(default_factory=list)
    metrics_summary: dict[str, Any] = Field(default_factory=dict)


class DeFiScoreRequest(BaseModel):
    """Request model for scoring a DeFi protocol."""

    protocol_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        pattern=r"^[a-zA-Z0-9_-]+$",
    )
    category: DeFiCategory
    smart_contract: SmartContractRisk = Field(default_factory=SmartContractRisk)
    economic: EconomicRisk = Field(default_factory=EconomicRisk)
    oracle: OracleRisk = Field(default_factory=OracleRisk)
    governance: GovernanceRisk = Field(default_factory=GovernanceRisk)


# ---------------------------------------------------------------------------
# Console research schemas (merged under /research prefix)
# ---------------------------------------------------------------------------


class ProtocolInfo(BaseModel):
    """DeFi protocol information."""

    protocol_id: str
    name: str
    category: str
    chains: list[str]
    tvl_usd: float
    tvl_change_24h: float
    risk_grade: str
    last_updated: datetime


class ProtocolsResponse(BaseModel):
    """Response model for protocols endpoint."""

    total_tvl_usd: float
    protocols: list[ProtocolInfo]
    as_of: datetime


class TokenomicsInfo(BaseModel):
    """Token economics information."""

    token_symbol: str
    token_name: str
    chain: str
    total_supply: float
    circulating_supply: float
    market_cap_usd: float
    fully_diluted_valuation_usd: float
    inflation_rate: float | None = None
    staking_ratio: float | None = None


class TokenomicsResponse(BaseModel):
    """Response model for tokenomics endpoint."""

    tokens: list[TokenomicsInfo]
    as_of: datetime

"""Protocol risk assessment schemas.

Pydantic models for blockchain protocol risk scoring based on:
- Consensus mechanism characteristics
- Decentralization metrics
- Settlement finality guarantees
- Operational metrics
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ConsensusMechanism(StrEnum):
    """Blockchain consensus mechanisms."""

    POW = "proof_of_work"
    POS = "proof_of_stake"
    DPOS = "delegated_proof_of_stake"
    POA = "proof_of_authority"
    POH = "proof_of_history"
    PBFT = "practical_bft"
    HYBRID = "hybrid"


class SettlementFinality(StrEnum):
    """Settlement finality types for blockchain transactions."""

    PROBABILISTIC = "probabilistic"
    DETERMINISTIC = "deterministic"
    ECONOMIC = "economic"


class RiskTier(StrEnum):
    """Protocol risk tier classification."""

    TIER_1 = "tier_1"
    TIER_2 = "tier_2"
    TIER_3 = "tier_3"
    TIER_4 = "tier_4"


class ProtocolRiskProfile(BaseModel):
    """Protocol metrics for risk assessment."""

    protocol_id: str = Field(..., description="Protocol identifier")
    consensus: ConsensusMechanism
    finality_type: SettlementFinality
    validator_count: int = Field(..., ge=1, description="Number of active validators/miners")
    nakamoto_coefficient: int = Field(..., ge=1, description="Minimum entities to control 51%")
    top_10_stake_pct: float = Field(0.0, ge=0, le=100)
    finality_time_seconds: float = Field(..., gt=0, description="Time to transaction finality")
    tps_average: float = Field(..., gt=0, description="Average transactions per second")
    tps_peak: float = Field(..., gt=0, description="Peak transactions per second")
    uptime_30d_pct: float = Field(99.9, ge=0, le=100)
    major_incidents_12m: int = Field(0, ge=0)
    has_bug_bounty: bool = Field(True)
    audit_count: int = Field(0, ge=0)
    time_since_last_upgrade_days: int = Field(30, ge=0)
    total_staked_usd: float | None = Field(None, ge=0)
    slashing_enabled: bool = Field(True)


class ProtocolRiskAssessment(BaseModel):
    """Comprehensive protocol risk assessment result."""

    protocol_id: str
    risk_tier: RiskTier
    consensus_score: float = Field(..., ge=0, le=100)
    decentralization_score: float = Field(..., ge=0, le=100)
    settlement_score: float = Field(..., ge=0, le=100)
    operational_score: float = Field(..., ge=0, le=100)
    security_score: float = Field(..., ge=0, le=100)
    overall_score: float = Field(..., ge=0, le=100)
    risk_factors: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    regulatory_notes: list[str] = Field(default_factory=list)
    metrics_summary: dict[str, Any] = Field(default_factory=dict)


class ProtocolRiskRequest(BaseModel):
    """Request model for protocol risk assessment."""

    protocol_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Protocol identifier",
    )
    consensus: ConsensusMechanism
    finality_type: SettlementFinality
    validator_count: int = Field(..., ge=1, le=10_000_000, description="Number of active validators")
    nakamoto_coefficient: int = Field(..., ge=1, le=10_000, description="Min entities to control 51%")
    finality_time_seconds: float = Field(..., gt=0, le=86400, description="Time to finality (max 24h)")
    tps_average: float = Field(..., gt=0, le=1_000_000, description="Average TPS")
    tps_peak: float = Field(..., gt=0, le=10_000_000, description="Peak TPS")
    uptime_30d_pct: float = Field(99.9, ge=0, le=100)
    major_incidents_12m: int = Field(0, ge=0, le=1000)
    has_bug_bounty: bool = Field(True)
    audit_count: int = Field(0, ge=0, le=1000)
    time_since_last_upgrade_days: int = Field(30, ge=0, le=10000)
    top_10_stake_pct: float = Field(50.0, ge=0, le=100)
    total_staked_usd: float | None = Field(None, ge=0)
    slashing_enabled: bool = Field(True)

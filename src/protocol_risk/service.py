"""Blockchain protocol risk assessment service.

Business logic for protocol risk scoring based on:
- Consensus mechanism characteristics
- Decentralization metrics
- Settlement finality guarantees
- Operational metrics
"""

from __future__ import annotations

from typing import Any

from src.protocol_risk.constants import (
    CONSENSUS_BASE_SCORES,
    FINALITY_ADJUSTMENTS,
    PROTOCOL_DEFAULTS,
)
from src.protocol_risk.schemas import (
    ConsensusMechanism,
    ProtocolRiskAssessment,
    ProtocolRiskProfile,
    RiskTier,
    SettlementFinality,
)


def get_protocol_defaults(protocol_id: str) -> dict[str, Any] | None:
    """Get default configuration for a known protocol."""
    return PROTOCOL_DEFAULTS.get(protocol_id.lower())


def list_protocol_defaults() -> list[str]:
    """List available protocol default configurations."""
    return list(PROTOCOL_DEFAULTS.keys())


def list_consensus_types() -> list[str]:
    """List available consensus mechanism types."""
    return [c.value for c in ConsensusMechanism]


def _calculate_consensus_score(
    profile: ProtocolRiskProfile,
) -> tuple[float, list[str], list[str]]:
    """Calculate consensus mechanism score."""
    risks: list[str] = []
    strengths: list[str] = []

    score = CONSENSUS_BASE_SCORES.get(profile.consensus, 50.0)
    score += FINALITY_ADJUSTMENTS.get(profile.finality_type, 0.0)

    if profile.consensus == ConsensusMechanism.POW:
        strengths.append("Battle-tested PoW consensus with 15+ years of security")
        if profile.finality_time_seconds > 3600:
            risks.append("Long probabilistic finality time (>1 hour for high confidence)")
    elif profile.consensus == ConsensusMechanism.POS:
        if profile.slashing_enabled:
            strengths.append("Economic finality backed by slashing mechanism")
            score += 5
        else:
            risks.append("No slashing mechanism - reduced economic security")
            score -= 10
        if profile.total_staked_usd and profile.total_staked_usd > 10_000_000_000:
            strengths.append(f"High economic security (>${profile.total_staked_usd / 1e9:.0f}B staked)")
            score += 5
    elif profile.consensus == ConsensusMechanism.DPOS:
        risks.append("DPoS trades decentralization for throughput - governance concentration risk")
        if profile.validator_count < 50:
            risks.append(f"Limited validator set ({profile.validator_count}) - collusion risk")
            score -= 10
    elif profile.consensus == ConsensusMechanism.POA:
        risks.append("Proof of Authority relies on trusted validators - centralization risk")

    return min(100, max(0, score)), risks, strengths


def _calculate_decentralization_score(
    profile: ProtocolRiskProfile,
) -> tuple[float, list[str], list[str]]:
    """Calculate decentralization score based on validator distribution."""
    risks: list[str] = []
    strengths: list[str] = []
    score = 50.0

    if profile.nakamoto_coefficient >= 20:
        score += 30
        strengths.append(f"High Nakamoto coefficient ({profile.nakamoto_coefficient}) - strong decentralization")
    elif profile.nakamoto_coefficient >= 10:
        score += 20
        strengths.append(f"Good Nakamoto coefficient ({profile.nakamoto_coefficient})")
    elif profile.nakamoto_coefficient >= 5:
        score += 10
    else:
        risks.append(f"Low Nakamoto coefficient ({profile.nakamoto_coefficient}) - concentration risk")
        score -= 10

    if profile.validator_count >= 1000:
        score += 15
        strengths.append(f"Large validator set ({profile.validator_count:,})")
    elif profile.validator_count >= 100:
        score += 10
    elif profile.validator_count < 50:
        risks.append(f"Small validator set ({profile.validator_count}) - limited decentralization")
        score -= 15

    if profile.top_10_stake_pct > 60:
        risks.append(f"High concentration: top 10 control {profile.top_10_stake_pct:.0f}% of network")
        score -= 15
    elif profile.top_10_stake_pct > 40:
        score -= 5
    elif profile.top_10_stake_pct < 30:
        strengths.append("Well-distributed stake among validators")
        score += 10

    return min(100, max(0, score)), risks, strengths


def _calculate_settlement_score(
    profile: ProtocolRiskProfile,
) -> tuple[float, list[str], list[str]]:
    """Calculate settlement finality score."""
    risks: list[str] = []
    strengths: list[str] = []
    score = 50.0

    if profile.finality_time_seconds <= 2:
        score += 30
        strengths.append(
            f"Sub-second finality ({profile.finality_time_seconds}s) - suitable for high-frequency settlement"
        )
    elif profile.finality_time_seconds <= 60:
        score += 20
        strengths.append(f"Fast finality ({profile.finality_time_seconds}s)")
    elif profile.finality_time_seconds <= 600:
        score += 10
    else:
        risks.append(
            f"Slow finality ({profile.finality_time_seconds / 60:.0f} minutes) "
            "- not suitable for time-sensitive settlements"
        )
        score -= 10

    if profile.finality_type == SettlementFinality.DETERMINISTIC:
        strengths.append("Deterministic finality - no reorg risk after confirmation")
        score += 15
    elif profile.finality_type == SettlementFinality.ECONOMIC:
        score += 10
    elif profile.finality_type == SettlementFinality.PROBABILISTIC:
        risks.append("Probabilistic finality - transactions can theoretically be reorged")
        score -= 5

    return min(100, max(0, score)), risks, strengths


def _calculate_operational_score(
    profile: ProtocolRiskProfile,
) -> tuple[float, list[str], list[str]]:
    """Calculate operational reliability score."""
    risks: list[str] = []
    strengths: list[str] = []
    score = 50.0

    if profile.uptime_30d_pct >= 99.99:
        score += 25
        strengths.append(f"Excellent uptime ({profile.uptime_30d_pct}%)")
    elif profile.uptime_30d_pct >= 99.9:
        score += 20
    elif profile.uptime_30d_pct >= 99.0:
        score += 10
    else:
        risks.append(f"Uptime concerns ({profile.uptime_30d_pct}%) - reliability risk")
        score -= 20

    if profile.major_incidents_12m == 0:
        score += 15
        strengths.append("No major incidents in past 12 months")
    elif profile.major_incidents_12m <= 2:
        score += 5
        risks.append(f"{profile.major_incidents_12m} major incident(s) in past 12 months")
    else:
        risks.append(f"Frequent incidents ({profile.major_incidents_12m} in 12 months) - operational risk")
        score -= 15

    if profile.tps_average >= 1000:
        score += 10
        strengths.append(f"High throughput capacity ({profile.tps_average:.0f} TPS average)")
    elif profile.tps_average < 20:
        risks.append(f"Limited throughput ({profile.tps_average:.0f} TPS) - congestion risk")
        score -= 5

    return min(100, max(0, score)), risks, strengths


def _calculate_security_score(
    profile: ProtocolRiskProfile,
) -> tuple[float, list[str], list[str]]:
    """Calculate security posture score."""
    risks: list[str] = []
    strengths: list[str] = []
    score = 50.0

    if profile.has_bug_bounty:
        score += 15
        strengths.append("Active bug bounty program")
    else:
        risks.append("No bug bounty program - reduced security incentives")
        score -= 10

    if profile.audit_count >= 20:
        score += 20
        strengths.append(f"Extensively audited ({profile.audit_count} audits)")
    elif profile.audit_count >= 5:
        score += 10
    elif profile.audit_count == 0:
        risks.append("No security audits - unverified security")
        score -= 25

    if 30 <= profile.time_since_last_upgrade_days <= 180:
        score += 10
        strengths.append("Active development with stable upgrade cadence")
    elif profile.time_since_last_upgrade_days < 14:
        risks.append("Very recent upgrade - potential instability")
        score -= 5
    elif profile.time_since_last_upgrade_days > 365:
        risks.append("Stale protocol - may lack security patches")
        score -= 10

    return min(100, max(0, score)), risks, strengths


def _determine_risk_tier(overall_score: float, profile: ProtocolRiskProfile) -> RiskTier:
    """Determine risk tier from overall score and key metrics."""
    if overall_score >= 80 and profile.nakamoto_coefficient >= 4:
        if profile.protocol_id.lower() in ["bitcoin", "ethereum"]:
            return RiskTier.TIER_1
        if profile.validator_count >= 500 and profile.major_incidents_12m == 0:
            return RiskTier.TIER_1

    if overall_score >= 65:
        return RiskTier.TIER_2
    if overall_score >= 50:
        return RiskTier.TIER_3
    return RiskTier.TIER_4


def _generate_regulatory_notes(profile: ProtocolRiskProfile, risk_tier: RiskTier) -> list[str]:
    """Generate regulatory considerations based on profile."""
    notes: list[str] = []

    if profile.consensus == ConsensusMechanism.POS:
        notes.append("PoS staking may trigger securities analysis under SEC guidance")

    if profile.nakamoto_coefficient < 5:
        notes.append("Low decentralization may affect commodity vs security classification")

    if profile.finality_time_seconds > 600:
        notes.append("Long finality may not meet T+1 settlement requirements")

    if risk_tier == RiskTier.TIER_1:
        notes.append("Tier 1 protocol - suitable for institutional custody frameworks")
    elif risk_tier == RiskTier.TIER_4:
        notes.append("Tier 4 protocol - enhanced due diligence required for institutional use")

    return notes


def assess_protocol_risk(
    protocol_id: str,
    consensus: ConsensusMechanism,
    finality_type: SettlementFinality,
    validator_count: int,
    nakamoto_coefficient: int,
    finality_time_seconds: float,
    tps_average: float,
    tps_peak: float,
    uptime_30d_pct: float = 99.9,
    major_incidents_12m: int = 0,
    has_bug_bounty: bool = True,
    audit_count: int = 0,
    time_since_last_upgrade_days: int = 30,
    top_10_stake_pct: float = 50.0,
    total_staked_usd: float | None = None,
    slashing_enabled: bool = True,
) -> ProtocolRiskAssessment:
    """Assess blockchain protocol risk."""
    profile = ProtocolRiskProfile(
        protocol_id=protocol_id,
        consensus=consensus,
        finality_type=finality_type,
        validator_count=validator_count,
        nakamoto_coefficient=nakamoto_coefficient,
        top_10_stake_pct=top_10_stake_pct,
        finality_time_seconds=finality_time_seconds,
        tps_average=tps_average,
        tps_peak=tps_peak,
        uptime_30d_pct=uptime_30d_pct,
        major_incidents_12m=major_incidents_12m,
        has_bug_bounty=has_bug_bounty,
        audit_count=audit_count,
        time_since_last_upgrade_days=time_since_last_upgrade_days,
        total_staked_usd=total_staked_usd,
        slashing_enabled=slashing_enabled,
    )

    all_risks: list[str] = []
    all_strengths: list[str] = []

    consensus_score, c_risks, c_strengths = _calculate_consensus_score(profile)
    all_risks.extend(c_risks)
    all_strengths.extend(c_strengths)

    decentralization_score, d_risks, d_strengths = _calculate_decentralization_score(profile)
    all_risks.extend(d_risks)
    all_strengths.extend(d_strengths)

    settlement_score, s_risks, s_strengths = _calculate_settlement_score(profile)
    all_risks.extend(s_risks)
    all_strengths.extend(s_strengths)

    operational_score, o_risks, o_strengths = _calculate_operational_score(profile)
    all_risks.extend(o_risks)
    all_strengths.extend(o_strengths)

    security_score, sec_risks, sec_strengths = _calculate_security_score(profile)
    all_risks.extend(sec_risks)
    all_strengths.extend(sec_strengths)

    weights = {
        "consensus": 0.25,
        "decentralization": 0.20,
        "settlement": 0.20,
        "operational": 0.20,
        "security": 0.15,
    }

    overall_score = (
        consensus_score * weights["consensus"]
        + decentralization_score * weights["decentralization"]
        + settlement_score * weights["settlement"]
        + operational_score * weights["operational"]
        + security_score * weights["security"]
    )

    risk_tier = _determine_risk_tier(overall_score, profile)
    regulatory_notes = _generate_regulatory_notes(profile, risk_tier)

    return ProtocolRiskAssessment(
        protocol_id=protocol_id,
        risk_tier=risk_tier,
        consensus_score=round(consensus_score, 1),
        decentralization_score=round(decentralization_score, 1),
        settlement_score=round(settlement_score, 1),
        operational_score=round(operational_score, 1),
        security_score=round(security_score, 1),
        overall_score=round(overall_score, 1),
        risk_factors=all_risks,
        strengths=all_strengths,
        regulatory_notes=regulatory_notes,
        metrics_summary={
            "consensus": profile.consensus.value,
            "finality_type": profile.finality_type.value,
            "validator_count": profile.validator_count,
            "nakamoto_coefficient": profile.nakamoto_coefficient,
            "finality_time_seconds": profile.finality_time_seconds,
            "tps_average": profile.tps_average,
            "uptime_30d_pct": profile.uptime_30d_pct,
        },
    )

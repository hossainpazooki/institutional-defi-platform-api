"""DeFi protocol risk scoring service + research stubs.

Business logic for comprehensive risk assessment across:
- Smart contract risk (audits, upgradeability, admin functions)
- Economic risk (token concentration, treasury, impermanent loss)
- Oracle risk (providers, fallbacks, manipulation resistance)
- Governance risk (centralization, timelocks, multisig)

Also includes Console research stubs for protocol info and tokenomics.
"""

from __future__ import annotations

from datetime import UTC, datetime

from .constants import DEFI_PROTOCOL_DEFAULTS, REPUTABLE_AUDITORS
from .schemas import (
    DeFiCategory,
    DeFiRiskScore,
    EconomicRisk,
    GovernanceRisk,
    GovernanceType,
    OracleProvider,
    OracleRisk,
    ProtocolInfo,
    ProtocolsResponse,
    RiskGrade,
    SmartContractRisk,
    TokenomicsInfo,
    TokenomicsResponse,
)

# =============================================================================
# Score helpers
# =============================================================================


def _score_to_grade(score: float) -> RiskGrade:
    if score >= 85:
        return RiskGrade.A
    elif score >= 70:
        return RiskGrade.B
    elif score >= 55:
        return RiskGrade.C
    elif score >= 40:
        return RiskGrade.D
    else:
        return RiskGrade.F


def _calculate_smart_contract_score(
    risk: SmartContractRisk,
) -> tuple[float, list[str], list[str], list[str], list[str]]:
    score = 50.0
    critical: list[str] = []
    high: list[str] = []
    medium: list[str] = []
    strengths: list[str] = []

    # Audits
    if risk.audit_count >= 3:
        score += 15
        strengths.append(f"Multiple independent audits ({risk.audit_count})")
    elif risk.audit_count >= 1:
        score += 8
    else:
        high.append("No security audits performed")
        score -= 20

    # Reputable auditors bonus
    auditor_bonus = 0.0
    for auditor in risk.auditors:
        weight = REPUTABLE_AUDITORS.get(auditor.lower(), 0)
        auditor_bonus += weight * 5
    score += min(auditor_bonus, 15)
    if auditor_bonus > 10:
        strengths.append(f"Audited by reputable firms: {', '.join(risk.auditors[:3])}")

    # Formal verification
    if risk.formal_verification:
        score += 10
        strengths.append("Formal verification completed")

    # Audit recency
    if risk.last_audit_days_ago > 365:
        medium.append("Audit is over 1 year old")
        score -= 5
    elif risk.last_audit_days_ago > 180:
        score -= 2

    # Upgradeability
    if risk.is_upgradeable:
        if risk.upgrade_timelock_hours >= 48:
            score += 5
            strengths.append(f"{risk.upgrade_timelock_hours}h upgrade timelock")
        elif risk.upgrade_timelock_hours < 24:
            medium.append("Short upgrade timelock (<24h)")
            score -= 5
    else:
        score += 10
        strengths.append("Immutable contracts")

    # Admin powers
    if risk.admin_can_drain:
        critical.append("CRITICAL: Admin can drain user funds")
        score -= 30
    if risk.admin_can_pause and not risk.has_admin_functions:
        score += 5

    # Track record
    if risk.exploit_history_count > 0:
        if risk.total_exploit_loss_usd > 10_000_000:
            critical.append(f"Major exploit history: ${risk.total_exploit_loss_usd / 1e6:.0f}M lost")
            score -= 25
        else:
            high.append(f"Exploit history: {risk.exploit_history_count} incidents")
            score -= 15

    if risk.contract_age_days >= 365 and risk.exploit_history_count == 0:
        score += 10
        strengths.append("1+ year track record with no exploits")
    elif risk.contract_age_days < 90:
        medium.append("New protocol (<90 days)")
        score -= 5

    # TVL
    if risk.tvl_usd > 1_000_000_000:
        score += 5
        strengths.append(f"High TVL (${risk.tvl_usd / 1e9:.1f}B) - battle-tested")

    # Bug bounty
    if risk.bug_bounty_max_usd >= 1_000_000:
        score += 5
        strengths.append(f"${risk.bug_bounty_max_usd / 1e6:.0f}M bug bounty program")
    elif risk.bug_bounty_max_usd == 0:
        medium.append("No bug bounty program")
        score -= 3

    return min(100, max(0, score)), critical, high, medium, strengths


def _calculate_economic_score(
    risk: EconomicRisk,
    category: DeFiCategory,
) -> tuple[float, list[str], list[str], list[str], list[str]]:
    score = 50.0
    critical: list[str] = []
    high: list[str] = []
    medium: list[str] = []
    strengths: list[str] = []

    if risk.token_concentration_top10_pct > 80:
        high.append(f"High token concentration: top 10 hold {risk.token_concentration_top10_pct:.0f}%")
        score -= 15
    elif risk.token_concentration_top10_pct > 60:
        medium.append(f"Moderate token concentration ({risk.token_concentration_top10_pct:.0f}%)")
        score -= 5
    elif risk.token_concentration_top10_pct < 40:
        score += 10
        strengths.append("Well-distributed token supply")

    if risk.team_token_pct > 30:
        medium.append(f"High team allocation ({risk.team_token_pct:.0f}%)")
        score -= 5
    if risk.vesting_remaining_pct < 20 and risk.team_token_pct > 15:
        medium.append("Most team tokens already unlocked")
        score -= 5

    if risk.treasury_runway_months >= 36:
        score += 10
        strengths.append(f"{risk.treasury_runway_months:.0f} month treasury runway")
    elif risk.treasury_runway_months < 12:
        high.append(f"Short treasury runway ({risk.treasury_runway_months:.0f} months)")
        score -= 10

    if risk.treasury_diversified:
        score += 5
        strengths.append("Diversified treasury holdings")

    if risk.has_protocol_revenue and risk.revenue_30d_usd > 1_000_000:
        score += 10
        strengths.append(f"Strong protocol revenue (${risk.revenue_30d_usd / 1e6:.1f}M/30d)")
    elif not risk.has_protocol_revenue:
        medium.append("No protocol revenue model")
        score -= 5

    if category == DeFiCategory.LIQUIDITY_POOL and risk.has_impermanent_loss:
        medium.append("Impermanent loss exposure for LPs")

    if risk.has_liquidation_risk:
        if risk.max_leverage > 10:
            high.append(f"High leverage available ({risk.max_leverage}x) with liquidation risk")
            score -= 10
        else:
            medium.append("Liquidation risk present")

    if category == DeFiCategory.STABLECOIN and risk.token_concentration_top10_pct > 50:
        high.append("Stablecoin: High holder concentration risk")
        score -= 10

    return min(100, max(0, score)), critical, high, medium, strengths


def _calculate_oracle_score(
    risk: OracleRisk,
    category: DeFiCategory,
) -> tuple[float, list[str], list[str], list[str], list[str]]:
    score = 50.0
    critical: list[str] = []
    high: list[str] = []
    medium: list[str] = []
    strengths: list[str] = []

    if risk.primary_oracle == OracleProvider.CHAINLINK:
        score += 20
        strengths.append("Chainlink oracle (industry standard)")
    elif risk.primary_oracle == OracleProvider.PYTH:
        score += 15
        strengths.append("Pyth oracle (low latency)")
    elif risk.primary_oracle == OracleProvider.UNISWAP_TWAP:
        score += 10
    elif risk.primary_oracle == OracleProvider.CUSTOM:
        medium.append("Custom oracle implementation")
        score -= 5
    elif risk.primary_oracle == OracleProvider.NONE:
        if category in (DeFiCategory.DEX, DeFiCategory.LIQUIDITY_POOL):
            score += 15
            strengths.append("No oracle dependency (AMM-based pricing)")
        else:
            high.append("No oracle - potential pricing issues")
            score -= 15

    if risk.has_fallback_oracle:
        score += 10
        strengths.append("Fallback oracle configured")
    elif risk.primary_oracle != OracleProvider.NONE:
        medium.append("No fallback oracle")
        score -= 5

    if risk.oracle_update_frequency_seconds <= 60:
        score += 5
    elif risk.oracle_update_frequency_seconds > 3600:
        medium.append("Slow oracle updates (>1 hour)")
        score -= 5

    if risk.oracle_manipulation_resistant:
        score += 10
        strengths.append("Oracle manipulation resistance (TWAP/multi-source)")
    else:
        high.append("Potential oracle manipulation vulnerability")
        score -= 15

    if risk.oracle_decentralized:
        score += 5
    else:
        medium.append("Centralized oracle")
        score -= 5

    if risk.oracle_failure_count_12m > 0:
        high.append(f"Oracle failures in past 12m: {risk.oracle_failure_count_12m}")
        score -= 10 * risk.oracle_failure_count_12m

    return min(100, max(0, score)), critical, high, medium, strengths


def _calculate_governance_score(
    risk: GovernanceRisk,
) -> tuple[float, list[str], list[str], list[str], list[str]]:
    score = 50.0
    critical: list[str] = []
    high: list[str] = []
    medium: list[str] = []
    strengths: list[str] = []

    if risk.governance_type == GovernanceType.IMMUTABLE:
        score += 20
        strengths.append("Immutable contracts - no governance risk")
    elif risk.governance_type == GovernanceType.TOKEN_VOTING:
        score += 10
        if risk.governance_participation_pct >= 20:
            score += 5
            strengths.append(f"Active governance ({risk.governance_participation_pct:.0f}% participation)")
        elif risk.governance_participation_pct < 5:
            medium.append("Low governance participation")
            score -= 5
    elif risk.governance_type == GovernanceType.MULTISIG:
        if risk.multisig_threshold:
            parts = risk.multisig_threshold.split("/")
            if len(parts) == 2:
                required, total = int(parts[0]), int(parts[1])
                if required >= 3 and total >= 5:
                    score += 10
                    strengths.append(f"Robust multisig ({risk.multisig_threshold})")
                elif required < 2:
                    high.append(f"Weak multisig ({risk.multisig_threshold})")
                    score -= 10
        if risk.multisig_signers_doxxed:
            score += 5
            strengths.append("Multisig signers publicly known")
    elif risk.governance_type == GovernanceType.CENTRALIZED:
        critical.append("Centralized control - single point of failure")
        score -= 25

    if risk.has_timelock:
        if risk.timelock_hours >= 48:
            score += 10
            strengths.append(f"{risk.timelock_hours}h governance timelock")
        elif risk.timelock_hours >= 24:
            score += 5
        else:
            medium.append(f"Short timelock ({risk.timelock_hours}h)")
    else:
        high.append("No governance timelock")
        score -= 15

    if risk.has_emergency_admin:
        if risk.emergency_actions_12m > 3:
            high.append(f"Frequent emergency actions ({risk.emergency_actions_12m} in 12m)")
            score -= 10
        else:
            medium.append("Emergency admin powers exist")
            score -= 3
    else:
        score += 5

    return min(100, max(0, score)), critical, high, medium, strengths


def _generate_regulatory_flags(
    category: DeFiCategory,
    smart_contract: SmartContractRisk,
    economic: EconomicRisk,
    governance: GovernanceRisk,
    overall_grade: RiskGrade,
) -> list[str]:
    flags: list[str] = []

    if governance.governance_type == GovernanceType.CENTRALIZED:
        flags.append("SEC: Centralized control may indicate security classification")
    if economic.team_token_pct > 25:
        flags.append("SEC: High team allocation may affect Howey test analysis")
    if category == DeFiCategory.LENDING:
        flags.append("Regulatory: Lending protocol may require state licensing in US")
    if category == DeFiCategory.DERIVATIVES:
        flags.append("CFTC: Derivatives protocol subject to CFTC jurisdiction")
    if category == DeFiCategory.STABLECOIN:
        flags.append("GENIUS Act: Stablecoin requires reserve attestation")
    if category == DeFiCategory.BRIDGE:
        flags.append("AML/KYC: Bridge protocols face enhanced scrutiny for cross-chain transfers")
    if overall_grade in (RiskGrade.D, RiskGrade.F):
        flags.append("Risk: Protocol does not meet institutional due diligence standards")
    if smart_contract.exploit_history_count > 0:
        flags.append("Disclosure: Historical exploit must be disclosed to investors")
    if smart_contract.admin_can_drain:
        flags.append("Custody: Admin withdrawal capability creates custodial concerns")

    return flags


# =============================================================================
# Main scoring function (from Workbench)
# =============================================================================


def score_defi_protocol(
    protocol_id: str,
    category: DeFiCategory,
    smart_contract: SmartContractRisk,
    economic: EconomicRisk,
    oracle: OracleRisk,
    governance: GovernanceRisk,
) -> DeFiRiskScore:
    """Score a DeFi protocol across risk dimensions."""
    all_critical: list[str] = []
    all_high: list[str] = []
    all_medium: list[str] = []
    all_strengths: list[str] = []

    sc_score, sc_crit, sc_high, sc_med, sc_str = _calculate_smart_contract_score(smart_contract)
    all_critical.extend(sc_crit)
    all_high.extend(sc_high)
    all_medium.extend(sc_med)
    all_strengths.extend(sc_str)

    econ_score, econ_crit, econ_high, econ_med, econ_str = _calculate_economic_score(economic, category)
    all_critical.extend(econ_crit)
    all_high.extend(econ_high)
    all_medium.extend(econ_med)
    all_strengths.extend(econ_str)

    oracle_score, ora_crit, ora_high, ora_med, ora_str = _calculate_oracle_score(oracle, category)
    all_critical.extend(ora_crit)
    all_high.extend(ora_high)
    all_medium.extend(ora_med)
    all_strengths.extend(ora_str)

    gov_score, gov_crit, gov_high, gov_med, gov_str = _calculate_governance_score(governance)
    all_critical.extend(gov_crit)
    all_high.extend(gov_high)
    all_medium.extend(gov_med)
    all_strengths.extend(gov_str)

    # Weighted overall
    overall_score = sc_score * 0.35 + econ_score * 0.25 + oracle_score * 0.20 + gov_score * 0.20
    if all_critical:
        overall_score = min(overall_score, 35)

    overall_grade = _score_to_grade(overall_score)
    regulatory_flags = _generate_regulatory_flags(
        category,
        smart_contract,
        economic,
        governance,
        overall_grade,
    )

    return DeFiRiskScore(
        protocol_id=protocol_id,
        category=category,
        smart_contract_grade=_score_to_grade(sc_score),
        economic_grade=_score_to_grade(econ_score),
        oracle_grade=_score_to_grade(oracle_score),
        governance_grade=_score_to_grade(gov_score),
        overall_grade=overall_grade,
        overall_score=round(overall_score, 1),
        smart_contract_score=round(sc_score, 1),
        economic_score=round(econ_score, 1),
        oracle_score=round(oracle_score, 1),
        governance_score=round(gov_score, 1),
        critical_risks=all_critical,
        high_risks=all_high,
        medium_risks=all_medium,
        strengths=all_strengths,
        regulatory_flags=regulatory_flags,
        metrics_summary={
            "category": category.value,
            "tvl_usd": smart_contract.tvl_usd,
            "audit_count": smart_contract.audit_count,
            "contract_age_days": smart_contract.contract_age_days,
            "governance_type": governance.governance_type.value,
        },
    )


def get_protocol_defaults(protocol_id: str) -> dict | None:
    """Get default configuration for a known protocol."""
    return DEFI_PROTOCOL_DEFAULTS.get(protocol_id.lower())


def list_protocol_defaults() -> list[str]:
    """List available protocol default configurations."""
    return list(DEFI_PROTOCOL_DEFAULTS.keys())


# =============================================================================
# Console research stubs
# =============================================================================


class DeFiResearchService:
    """Research service for protocol info and tokenomics (from Console)."""

    async def get_protocols(self) -> ProtocolsResponse:
        now = datetime.now(tz=UTC)
        return ProtocolsResponse(
            total_tvl_usd=150_000_000_000,
            protocols=[
                ProtocolInfo(
                    protocol_id="aave_v3",
                    name="Aave V3",
                    category="lending",
                    chains=["ethereum", "polygon", "arbitrum", "base"],
                    tvl_usd=15_000_000_000,
                    tvl_change_24h=2.5,
                    risk_grade="A",
                    last_updated=now,
                ),
                ProtocolInfo(
                    protocol_id="uniswap_v3",
                    name="Uniswap V3",
                    category="dex",
                    chains=["ethereum", "polygon", "arbitrum", "base", "optimism"],
                    tvl_usd=5_000_000_000,
                    tvl_change_24h=-1.2,
                    risk_grade="A",
                    last_updated=now,
                ),
                ProtocolInfo(
                    protocol_id="lido",
                    name="Lido",
                    category="liquid_staking",
                    chains=["ethereum"],
                    tvl_usd=35_000_000_000,
                    tvl_change_24h=0.5,
                    risk_grade="A",
                    last_updated=now,
                ),
                ProtocolInfo(
                    protocol_id="compound_v3",
                    name="Compound V3",
                    category="lending",
                    chains=["ethereum", "base", "arbitrum"],
                    tvl_usd=3_000_000_000,
                    tvl_change_24h=1.8,
                    risk_grade="A",
                    last_updated=now,
                ),
                ProtocolInfo(
                    protocol_id="gmx",
                    name="GMX",
                    category="derivatives",
                    chains=["arbitrum", "avalanche"],
                    tvl_usd=500_000_000,
                    tvl_change_24h=3.2,
                    risk_grade="B",
                    last_updated=now,
                ),
            ],
            as_of=now,
        )

    async def get_tokenomics(self) -> TokenomicsResponse:
        now = datetime.now(tz=UTC)
        return TokenomicsResponse(
            tokens=[
                TokenomicsInfo(
                    token_symbol="ETH",
                    token_name="Ethereum",
                    chain="ethereum",
                    total_supply=120_000_000,
                    circulating_supply=120_000_000,
                    market_cap_usd=400_000_000_000,
                    fully_diluted_valuation_usd=400_000_000_000,
                    inflation_rate=-0.5,
                    staking_ratio=0.27,
                ),
                TokenomicsInfo(
                    token_symbol="AAVE",
                    token_name="Aave",
                    chain="ethereum",
                    total_supply=16_000_000,
                    circulating_supply=14_500_000,
                    market_cap_usd=2_000_000_000,
                    fully_diluted_valuation_usd=2_200_000_000,
                ),
            ],
            as_of=now,
        )

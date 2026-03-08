"""Token compliance analysis service.

Implements SEC Howey Test and GENIUS Act stablecoin provisions
for regulatory classification of digital assets.
"""

from __future__ import annotations

from src.token_compliance.schemas import (
    GeniusActAnalysis,
    HoweyTestResult,
    TokenClassification,
    TokenComplianceResult,
    TokenStandard,
)

# Permitted reserve assets under GENIUS Act
PERMITTED_RESERVE_ASSETS = {
    "usd_cash",
    "us_treasury_bills",
    "us_treasury_notes",
    "reverse_repo",
    "money_market_funds",
    "insured_deposits",
}


def apply_howey_test(
    *,
    investment_of_money: bool,
    common_enterprise: bool,
    expectation_of_profits: bool,
    efforts_of_others: bool,
    decentralization_score: float = 0.0,
    is_functional_network: bool = False,
) -> HoweyTestResult:
    """Apply SEC Howey Test to determine security classification."""
    notes: list[str] = []

    adjusted_efforts_of_others = efforts_of_others
    if decentralization_score >= 0.8 and is_functional_network:
        adjusted_efforts_of_others = False
        notes.append(
            "Network deemed sufficiently decentralized - 'efforts of others' prong not satisfied per SEC guidance"
        )

    if expectation_of_profits and not efforts_of_others:
        notes.append(
            "Profit expectation exists but not derived from others' efforts - "
            "may qualify as commodity rather than security"
        )

    return HoweyTestResult(
        investment_of_money=investment_of_money,
        common_enterprise=common_enterprise,
        expectation_of_profits=expectation_of_profits,
        efforts_of_others=adjusted_efforts_of_others,
        analysis_notes=notes,
        decentralization_factor=decentralization_score,
    )


def analyze_genius_act_compliance(
    *,
    is_stablecoin: bool,
    pegged_currency: str,
    reserve_assets: list[str],
    reserve_ratio: float,
    uses_algorithmic_mechanism: bool,
    issuer_charter_type: str,
    has_reserve_attestation: bool,
    attestation_frequency_days: int = 0,
) -> GeniusActAnalysis:
    """Analyze compliance with GENIUS Act stablecoin provisions."""
    notes: list[str] = []

    is_payment_stablecoin = is_stablecoin and pegged_currency == "USD"

    reserve_set = {ra.lower().replace(" ", "_") for ra in reserve_assets}
    backed_by_permitted = reserve_set.issubset(PERMITTED_RESERVE_ASSETS)

    if not backed_by_permitted:
        unpermitted = reserve_set - PERMITTED_RESERVE_ASSETS
        notes.append(f"Reserve contains non-permitted assets: {unpermitted}")

    has_one_to_one = reserve_ratio >= 1.0
    if not has_one_to_one:
        notes.append(f"Reserve ratio {reserve_ratio:.2%} is below 1:1 requirement")

    if uses_algorithmic_mechanism:
        notes.append("Algorithmic stabilization mechanism prohibited under GENIUS Act")

    reserve_transparent = has_reserve_attestation and attestation_frequency_days <= 30
    if not reserve_transparent:
        notes.append("Monthly reserve attestation required")

    if not is_payment_stablecoin:
        compliance_status = "not_applicable"
    elif uses_algorithmic_mechanism:
        compliance_status = "prohibited"
    elif backed_by_permitted and has_one_to_one and reserve_transparent:
        compliance_status = "compliant"
    else:
        compliance_status = "requires_remediation"

    return GeniusActAnalysis(
        is_payment_stablecoin=is_payment_stablecoin,
        backed_by_permitted_assets=backed_by_permitted,
        has_one_to_one_backing=has_one_to_one,
        is_algorithmic=uses_algorithmic_mechanism,
        issuer_type=issuer_charter_type,
        reserve_transparency=reserve_transparent,
        compliance_status=compliance_status,
        compliance_notes=notes,
    )


def analyze_token_compliance(
    *,
    standard: TokenStandard,
    has_profit_expectation: bool,
    is_decentralized: bool,
    backed_by_fiat: bool,
    investment_of_money: bool = True,
    common_enterprise: bool = True,
    efforts_of_promoter: bool = True,
    decentralization_score: float = 0.0,
    is_functional_network: bool = False,
    is_stablecoin: bool = False,
    pegged_currency: str = "USD",
    reserve_assets: list[str] | None = None,
    reserve_ratio: float = 1.0,
    uses_algorithmic_mechanism: bool = False,
    issuer_charter_type: str = "non_bank_qualified",
    has_reserve_attestation: bool = False,
    attestation_frequency_days: int = 30,
) -> TokenComplianceResult:
    """Comprehensive token compliance analysis for US regulatory requirements."""
    compliance_requirements: list[str] = []
    regulatory_risks: list[str] = []
    recommended_actions: list[str] = []

    howey_result = apply_howey_test(
        investment_of_money=investment_of_money,
        common_enterprise=common_enterprise,
        expectation_of_profits=has_profit_expectation,
        efforts_of_others=efforts_of_promoter,
        decentralization_score=decentralization_score,
        is_functional_network=is_functional_network,
    )

    genius_result = None
    if is_stablecoin or backed_by_fiat:
        genius_result = analyze_genius_act_compliance(
            is_stablecoin=is_stablecoin or backed_by_fiat,
            pegged_currency=pegged_currency,
            reserve_assets=reserve_assets or ["usd_cash"],
            reserve_ratio=reserve_ratio,
            uses_algorithmic_mechanism=uses_algorithmic_mechanism,
            issuer_charter_type=issuer_charter_type,
            has_reserve_attestation=has_reserve_attestation,
            attestation_frequency_days=attestation_frequency_days,
        )

    if standard == TokenStandard.ERC_721:
        classification = TokenClassification.NFT
        sec_jurisdiction = False
        cftc_jurisdiction = False
    elif genius_result and genius_result.is_payment_stablecoin:
        classification = TokenClassification.PAYMENT_STABLECOIN
        sec_jurisdiction = False
        cftc_jurisdiction = False
        if genius_result.compliance_status != "compliant":
            compliance_requirements.append("Obtain GENIUS Act compliant status")
            regulatory_risks.append("Operating as non-compliant stablecoin")
    elif howey_result.is_security:
        classification = TokenClassification.SECURITY_TOKEN
        sec_jurisdiction = True
        cftc_jurisdiction = False
        compliance_requirements.extend(
            [
                "Register with SEC or qualify for exemption",
                "Comply with Securities Act of 1933",
                "File periodic reports under Exchange Act",
            ]
        )
        regulatory_risks.append("Unregistered securities offering liability")
    elif has_profit_expectation and not howey_result.is_security:
        classification = TokenClassification.COMMODITY_TOKEN
        sec_jurisdiction = False
        cftc_jurisdiction = True
        compliance_requirements.append("Comply with CFTC anti-fraud provisions")
    else:
        classification = TokenClassification.UTILITY_TOKEN
        sec_jurisdiction = False
        cftc_jurisdiction = False

    requires_sec = classification == TokenClassification.SECURITY_TOKEN
    genius_applicable = genius_result is not None and genius_result.is_payment_stablecoin

    if requires_sec:
        recommended_actions.append("Consult securities counsel for registration options")
        recommended_actions.append("Consider Regulation D or Regulation A+ exemptions")
    if genius_applicable and genius_result is not None and genius_result.compliance_status != "compliant":
        recommended_actions.append("Work with qualified issuer to achieve GENIUS Act compliance")

    return TokenComplianceResult(
        standard=standard,
        classification=classification,
        requires_sec_registration=requires_sec,
        genius_act_applicable=genius_applicable,
        howey_analysis=howey_result,
        genius_analysis=genius_result,
        compliance_requirements=compliance_requirements,
        regulatory_risks=regulatory_risks,
        recommended_actions=recommended_actions,
        sec_jurisdiction=sec_jurisdiction,
        cftc_jurisdiction=cftc_jurisdiction,
    )


def list_token_standards() -> list[str]:
    """List supported token standards."""
    return [s.value for s in TokenStandard]

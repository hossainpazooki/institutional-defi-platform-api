"""JPM Scenarios business logic service."""

from __future__ import annotations

from datetime import UTC, datetime

from src.jpm_scenarios.constants import CHAIN_PROFILES, SCENARIOS, ScenarioConfig
from src.jpm_scenarios.schemas import (
    ExplanationResult,
    MemoResponse,
    ScenarioRunResult,
    ScenariosResponse,
    ScenarioSummary,
)


class JPMScenarioService:
    """Service for executing JPM tokenization scenarios."""

    def list_scenarios(self) -> ScenariosResponse:
        """List all available JPM tokenization scenarios."""
        scenarios = [
            ScenarioSummary(
                id=s["id"],
                name=s["name"],
                description=s["description"],
                chain=s["chain"],
                instrument_type=s["instrument_type"],
                jurisdictions=s["jurisdictions"],
                defi_protocols=s["defi_protocols"],
            )
            for s in SCENARIOS.values()
        ]
        return ScenariosResponse(scenarios=scenarios, count=len(scenarios))

    def get_scenario(self, scenario_id: str) -> ScenarioConfig | None:
        """Get details of a specific scenario."""
        return SCENARIOS.get(scenario_id)

    def run_scenario(self, scenario_id: str) -> ScenarioRunResult | None:
        """Execute a JPM scenario through the full risk pipeline.

        Steps:
        1. Protocol/chain risk assessment
        2. DeFi protocol risk (if applicable)
        3. Market risk assessment
        4. Compliance/regulatory pathway
        5. Decoder explanation
        """
        config = SCENARIOS.get(scenario_id)
        if config is None:
            return None

        chain_profile = CHAIN_PROFILES.get(config["chain"], {})

        # Build mock results
        results = {
            "protocol_risk": {
                "profile": chain_profile,
                "recommendations": _get_chain_recommendations(config["chain"]),
                "computed_at": datetime.now(UTC).isoformat(),
            },
            "market_risk": {
                "var_99": 2_500_000,
                "var_99_10d": 7_900_000,
                "cvar_99": 3_200_000,
                "exposure_usd": 100_000_000,
                "volatility_30d": 0.45,
            },
            "compliance": {
                "status": "approved" if not config["defi_protocols"] else "conditional",
                "jurisdictions": config["jurisdictions"],
                "conflicts": [],
                "requirements": _get_compliance_requirements(config["jurisdictions"]),
            },
        }

        # Add DeFi risk if applicable
        if config["defi_protocols"]:
            results["defi_risk"] = {
                proto: {
                    "overall_score": 90,
                    "smart_contract_score": 95,
                    "economic_score": 88,
                    "grade": "A",
                }
                for proto in config["defi_protocols"]
            }

        # Calculate overall risk score
        overall_score = chain_profile.get("overall_score", 75)
        if config["defi_protocols"]:
            overall_score = (overall_score + 90) / 2  # Average with DeFi score

        # Stub explanation
        explanation = ExplanationResult(
            decision="APPROVED" if overall_score >= 70 else "REQUIRES_REVIEW",
            confidence=0.85,
            explanation=(
                f"Scenario '{config['name']}' has been assessed with an overall risk score of {overall_score:.0f}/100. "
                f"The {config['chain']} chain has a {chain_profile.get('risk_tier', 'medium')} risk tier."
            ),
            citations=[
                {
                    "source": "protocol_risk.overall_score",
                    "text": f"Chain score: {chain_profile.get('overall_score', 75)}",
                },
                {"source": "protocol_risk.risk_tier", "text": f"Risk tier: {chain_profile.get('risk_tier', 'medium')}"},
            ],
            tier="anchored",
        )

        return ScenarioRunResult(
            scenario_id=scenario_id,
            scenario_name=config["name"],
            timestamp=datetime.now(UTC),
            results=results,
            explanation=explanation,
            recommendations=_get_scenario_recommendations(scenario_id, config),
            overall_risk_score=overall_score,
        )

    def generate_memo(self, scenario_id: str, fmt: str = "markdown") -> MemoResponse | None:
        """Generate an audit-ready memo for a scenario."""
        config = SCENARIOS.get(scenario_id)
        if config is None:
            return None

        chain_profile = CHAIN_PROFILES.get(config["chain"], {})

        # Generate markdown memo
        memo_content = f"""# Risk Assessment Memo: {config["name"]}

## Executive Summary

This memo documents the risk assessment for the **{config["name"]}** tokenization scenario.

**Assessment Date:** {datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")}
**Overall Risk Score:** {chain_profile.get("overall_score", 75)}/100
**Risk Tier:** {chain_profile.get("risk_tier", "medium").upper()}
**Recommendation:** {"APPROVED" if chain_profile.get("overall_score", 75) >= 70 else "REQUIRES_REVIEW"}

## Scenario Details

- **Instrument Type:** {config["instrument_type"]}
- **Target Chain:** {config["chain"].title()}
- **Jurisdictions:** {", ".join(config["jurisdictions"])}
- **DeFi Integration:** {"Yes - " + ", ".join(config["defi_protocols"]) if config["defi_protocols"] else "No"}

## Chain Risk Assessment

| Metric | Score |
|--------|-------|
| Overall Score | {chain_profile.get("overall_score", 75)}/100 |
| Decentralization | {chain_profile.get("decentralization_score", 70)}/100 |
| Security | {chain_profile.get("security_score", 80)}/100 |
| Finality | {chain_profile.get("finality_score", 80)}/100 |
| Operational | {chain_profile.get("operational_score", 85)}/100 |

**Finality Time:** {chain_profile.get("finality_seconds", 60)} seconds

## Recommendations

{chr(10).join("- " + rec for rec in _get_scenario_recommendations(scenario_id, config))}

## Compliance Notes

Approved for the following jurisdictions: {", ".join(config["jurisdictions"])}

---

*Generated by Crypto Risk Gate v3 - Decoder Service*
*This is a stub memo. Full LLM-generated analysis requires Anthropic API configuration.*
"""

        if fmt == "pdf":
            memo_content = "PDF generation is a stub. Base64 content would be here."

        return MemoResponse(
            scenario_id=scenario_id,
            scenario_name=config["name"],
            format=fmt,
            content=memo_content,
            generated_at=datetime.now(UTC),
        )


def _get_chain_recommendations(chain: str) -> list[str]:
    """Get recommendations based on chain."""
    recs = {
        "base": [
            "Monitor Base sequencer uptime",
            "Implement L1 fallback for critical operations",
            "Track Coinbase operational status",
        ],
        "solana": [
            "Monitor Solana validator health",
            "Implement multi-RPC redundancy",
            "Track network performance during high load",
        ],
        "polygon": [
            "Monitor checkpoint submissions to Ethereum",
            "Track validator set changes",
        ],
        "ethereum": [
            "Standard confirmation wait times recommended",
            "Monitor gas prices for transaction timing",
        ],
        "canton": [
            "Verify permissioned network access",
            "Monitor node operator status",
        ],
    }
    return recs.get(chain, ["Standard monitoring recommended"])


def _get_compliance_requirements(jurisdictions: list[str]) -> list[str]:
    """Get compliance requirements for jurisdictions."""
    reqs = []
    if "US" in jurisdictions:
        reqs.extend(["SEC registration review", "CFTC derivatives compliance", "FinCEN AML requirements"])
    if "EU" in jurisdictions:
        reqs.extend(["MiCA compliance assessment", "AMLD6 AML requirements"])
    if "UK" in jurisdictions:
        reqs.extend(["FCA registration", "Financial promotions approval"])
    if "SG" in jurisdictions:
        reqs.extend(["MAS licensing review", "Payment Services Act compliance"])
    return reqs


def _get_scenario_recommendations(scenario_id: str, config: ScenarioConfig) -> list[str]:
    """Get scenario-specific recommendations."""
    recs = _get_chain_recommendations(config["chain"])

    if config["defi_protocols"]:
        recs.extend(
            [
                "Monitor DeFi protocol governance proposals",
                "Set up oracle deviation alerts for Chainlink price feeds",
                "Track smart contract upgrade proposals",
            ]
        )

    if config["instrument_type"] == "deposit_token":
        recs.append("Implement real-time reserve monitoring")
    elif config["instrument_type"] == "tokenized_fund":
        recs.append("Ensure NAV oracle accuracy monitoring")
    elif config["instrument_type"] == "tokenized_bond":
        recs.append("Monitor issuer credit events")

    return recs

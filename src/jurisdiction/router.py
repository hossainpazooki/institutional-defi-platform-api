"""Unified jurisdiction API routes.

Combines:
- Workbench routes_navigate.py: /navigate endpoints (cross-border compliance)
- Console compliance/router.py: /compliance endpoints (regulatory status, sanctions)
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter

from .conflicts import detect_conflicts
from .evaluator import evaluate_jurisdiction
from .pathway import aggregate_obligations, estimate_timeline, synthesize_pathway
from .resolver import get_equivalences, resolve_jurisdictions
from .schemas import (
    JurisdictionInfo,
    JurisdictionRoleResponse,
    JurisdictionsResponse,
    NavigateRequest,
    NavigateResponse,
    SanctionCheckResult,
    SanctionsResponse,
)

# =============================================================================
# Router Setup
# =============================================================================

navigate_router = APIRouter(prefix="/navigate", tags=["navigate"])
compliance_router = APIRouter(prefix="/compliance", tags=["compliance"])


# =============================================================================
# Navigate Endpoints (from Workbench routes_navigate.py)
# =============================================================================


@navigate_router.post("", response_model=NavigateResponse)
async def navigate(request: NavigateRequest) -> NavigateResponse:
    """Navigate cross-border compliance requirements.

    Implements v4 Flow 3: Cross-Border Navigation (Sync, Multi-Jurisdiction)
    """
    audit_trail: list[dict[str, Any]] = []

    # Step 1: Resolve jurisdictions and regimes
    audit_trail.append(
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "action": "NAVIGATE_REQUEST",
            "details": {
                "issuer": request.issuer_jurisdiction,
                "targets": request.target_jurisdictions,
                "instrument": request.instrument_type,
                "activity": request.activity,
            },
        }
    )

    applicable = resolve_jurisdictions(
        issuer=request.issuer_jurisdiction,
        targets=request.target_jurisdictions,
        instrument_type=request.instrument_type,
    )

    audit_trail.append(
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "action": "JURISDICTION_RESOLUTION",
            "details": {
                "applicable_count": len(applicable),
                "jurisdictions": [j.jurisdiction.value for j in applicable],
            },
        }
    )

    # Step 2: Get equivalence determinations
    equivalences = get_equivalences(
        from_jurisdiction=request.issuer_jurisdiction,
        to_jurisdictions=request.target_jurisdictions,
    )

    if equivalences:
        audit_trail.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "action": "EQUIVALENCE_CHECK",
                "details": {"equivalences": equivalences},
            }
        )

    # Market Risk Enhancements: Token compliance analysis
    token_compliance_result = None
    if request.token_standard:
        token_compliance_result = _analyze_token_compliance(request, audit_trail)

    # Market Risk Enhancements: Protocol risk assessment
    protocol_risk_result = None
    if request.underlying_chain:
        protocol_risk_result = _assess_protocol_risk(request, audit_trail)

    # Market Risk Enhancements: DeFi risk scoring
    defi_risk_result = None
    if request.is_defi_integrated and request.defi_protocol:
        defi_risk_result = _score_defi_risk(request, audit_trail)

    # Step 3: Parallel evaluation across all jurisdictions
    evaluation_tasks = [
        evaluate_jurisdiction(
            jurisdiction=j.jurisdiction.value,
            regime_id=j.regime_id,
            facts={
                **request.facts,
                "instrument_type": request.instrument_type,
                "activity": request.activity,
                "investor_types": request.investor_types,
                "target_jurisdiction": j.jurisdiction.value,
            },
        )
        for j in applicable
    ]

    jurisdiction_results = await asyncio.gather(*evaluation_tasks)

    # Add role to results
    for i, result in enumerate(jurisdiction_results):
        result["role"] = applicable[i].role.value

    for result in jurisdiction_results:
        audit_trail.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "action": f"EVALUATE_{result['jurisdiction']}",
                "details": {
                    "regime": result["regime_id"],
                    "rules_evaluated": result["rules_evaluated"],
                    "status": result["status"],
                },
            }
        )

    # Step 4: Detect conflicts between jurisdictions
    conflicts = detect_conflicts(jurisdiction_results)

    if conflicts:
        audit_trail.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "action": "CONFLICT_DETECTION",
                "details": {"conflicts_found": len(conflicts)},
            }
        )

    # Step 5: Synthesize compliance pathway
    pathway = synthesize_pathway(
        results=jurisdiction_results,
        conflicts=conflicts,
        equivalences=equivalences,
    )

    # Step 6: Aggregate obligations across jurisdictions
    cumulative_obligations = aggregate_obligations(jurisdiction_results)

    # Determine overall status
    if any(c.get("severity") == "blocking" for c in conflicts):
        status = "blocked"
    elif any(c.get("severity") == "warning" for c in conflicts):
        status = "requires_review"
    elif any(jr.get("status") == "blocked" for jr in jurisdiction_results):
        status = "blocked"
    else:
        status = "actionable"

    return NavigateResponse(
        status=status,
        applicable_jurisdictions=[
            JurisdictionRoleResponse(
                jurisdiction=j.jurisdiction.value,
                regime_id=j.regime_id,
                role=j.role.value,
            )
            for j in applicable
        ],
        jurisdiction_results=jurisdiction_results,
        conflicts=conflicts,
        pathway=pathway,
        cumulative_obligations=cumulative_obligations,
        estimated_timeline=estimate_timeline(pathway),
        audit_trail=audit_trail,
        token_compliance=token_compliance_result,
        protocol_risk=protocol_risk_result,
        defi_risk=defi_risk_result,
    )


@navigate_router.get("/jurisdictions")
async def list_jurisdictions() -> dict:
    """List all supported jurisdictions."""
    from src.database import get_db

    try:
        with get_db() as conn:
            from sqlalchemy import text

            cursor = conn.execute(text("SELECT code, name, authority FROM jurisdictions"))
            jurisdictions = [{"code": row[0], "name": row[1], "authority": row[2]} for row in cursor.fetchall()]
        return {"jurisdictions": jurisdictions}
    except Exception:
        # Fallback: return hardcoded list from ontology
        from src.ontology.jurisdiction import JURISDICTION_AUTHORITIES, JURISDICTION_NAMES, JurisdictionCode

        jurisdictions = [
            {
                "code": code.value,
                "name": JURISDICTION_NAMES.get(code, code.value),
                "authority": JURISDICTION_AUTHORITIES.get(code, "Unknown"),
            }
            for code in JurisdictionCode
        ]
        return {"jurisdictions": jurisdictions}


@navigate_router.get("/regimes")
async def list_regimes() -> dict:
    """List all regulatory regimes."""
    from src.database import get_db

    try:
        with get_db() as conn:
            from sqlalchemy import text

            cursor = conn.execute(
                text("""
                SELECT id, jurisdiction_code, name, effective_date
                FROM regulatory_regimes
                ORDER BY jurisdiction_code, effective_date DESC
                """)
            )
            regimes = [
                {
                    "id": row[0],
                    "jurisdiction_code": row[1],
                    "name": row[2],
                    "effective_date": row[3],
                }
                for row in cursor.fetchall()
            ]
        return {"regimes": regimes}
    except Exception:
        # Fallback: return default regime mappings
        from .constants import DEFAULT_REGIMES

        regimes = [
            {"id": regime_id, "jurisdiction_code": code, "name": regime_id, "effective_date": None}
            for code, regime_id in DEFAULT_REGIMES.items()
        ]
        return {"regimes": regimes}


@navigate_router.get("/equivalences")
async def list_equivalences() -> dict:
    """List all equivalence determinations."""
    from src.database import get_db

    try:
        with get_db() as conn:
            from sqlalchemy import text

            cursor = conn.execute(
                text("""
                SELECT id, from_jurisdiction, to_jurisdiction, scope, status, notes
                FROM equivalence_determinations
                """)
            )
            equivalences = [
                {
                    "id": row[0],
                    "from_jurisdiction": row[1],
                    "to_jurisdiction": row[2],
                    "scope": row[3],
                    "status": row[4],
                    "notes": row[5],
                }
                for row in cursor.fetchall()
            ]
        return {"equivalences": equivalences}
    except Exception:
        return {"equivalences": []}


# =============================================================================
# Compliance Endpoints (from Console compliance/router.py)
# =============================================================================


@compliance_router.get("/jurisdictions", response_model=JurisdictionsResponse)
async def get_compliance_jurisdictions():
    """Get regulatory status by jurisdiction."""
    return JurisdictionsResponse(
        jurisdictions=[
            JurisdictionInfo(
                jurisdiction_code="US",
                name="United States",
                regulatory_status="developing",
                crypto_classification="commodity",
                key_requirements=[
                    "SEC registration for securities",
                    "CFTC oversight for derivatives",
                    "FinCEN AML/KYC requirements",
                    "State money transmitter licenses",
                ],
                last_updated=datetime.utcnow(),
            ),
            JurisdictionInfo(
                jurisdiction_code="EU",
                name="European Union",
                regulatory_status="clear",
                crypto_classification="other",
                key_requirements=[
                    "MiCA compliance",
                    "AMLD6 AML requirements",
                    "DORA operational resilience",
                ],
                last_updated=datetime.utcnow(),
            ),
            JurisdictionInfo(
                jurisdiction_code="UK",
                name="United Kingdom",
                regulatory_status="clear",
                crypto_classification="other",
                key_requirements=[
                    "FCA registration",
                    "Financial promotions approval",
                    "AML/KYC requirements",
                ],
                last_updated=datetime.utcnow(),
            ),
            JurisdictionInfo(
                jurisdiction_code="SG",
                name="Singapore",
                regulatory_status="clear",
                crypto_classification="other",
                key_requirements=[
                    "MAS licensing",
                    "Payment Services Act compliance",
                ],
                last_updated=datetime.utcnow(),
            ),
        ],
        as_of=datetime.utcnow(),
    )


@compliance_router.get("/sanctions", response_model=SanctionsResponse)
async def get_sanctions_status():
    """Get sanctions screening status."""
    return SanctionsResponse(
        results=[
            SanctionCheckResult(
                address="0x1234...5678",
                chain="ethereum",
                is_sanctioned=False,
                sanction_lists=[],
                risk_score=0.1,
                checked_at=datetime.utcnow(),
            ),
        ],
        total_checked=1000,
        flagged_count=0,
        as_of=datetime.utcnow(),
    )


@compliance_router.post("/sanctions/check")
async def check_address():
    """Check an address against sanction lists."""
    return {"status": "stub", "module": "compliance.sanctions.check"}


@compliance_router.get("/alerts")
async def get_compliance_alerts():
    """Get compliance alerts."""
    return {"status": "stub", "module": "compliance.alerts"}


@compliance_router.get("/reports")
async def get_compliance_reports():
    """Get compliance reports."""
    return {"status": "stub", "module": "compliance.reports"}


# =============================================================================
# Navigate Helper Functions (cross-domain integration)
# =============================================================================


def _analyze_token_compliance(request: NavigateRequest, audit_trail: list[dict]) -> dict | None:
    """Run token compliance analysis if token_standard is provided."""
    try:
        from src.token_compliance.schemas import TokenStandard
        from src.token_compliance.service import analyze_token_compliance

        token_standard_map = {
            "erc-20": TokenStandard.ERC_20,
            "erc-721": TokenStandard.ERC_721,
            "erc-1155": TokenStandard.ERC_1155,
            "bep-20": TokenStandard.BEP_20,
            "spl": TokenStandard.SPL,
            "trc-20": TokenStandard.TRC_20,
        }
        standard_key = request.token_standard.lower()
        token_standard_enum = token_standard_map.get(standard_key, TokenStandard.ERC_20)

        is_stablecoin = request.instrument_type in ["stablecoin", "payment_stablecoin"]
        is_security_like = request.instrument_type in [
            "tokenized_bond",
            "security_token",
            "tokenized_equity",
        ]

        compliance_result = analyze_token_compliance(
            standard=token_standard_enum,
            has_profit_expectation=is_security_like or request.facts.get("has_profit_expectation", False),
            is_decentralized=request.facts.get("is_decentralized", not is_security_like),
            backed_by_fiat=is_stablecoin or request.facts.get("backed_by_fiat", False),
            investment_of_money=request.facts.get("investment_of_money", True),
            common_enterprise=request.facts.get("common_enterprise", is_security_like),
            efforts_of_promoter=request.facts.get("efforts_of_promoter", is_security_like),
            decentralization_score=request.facts.get("decentralization_score", 0.5 if not is_security_like else 0.1),
            is_functional_network=request.facts.get("is_functional_network", not is_security_like),
            is_stablecoin=is_stablecoin,
            pegged_currency=request.facts.get("pegged_currency", "USD"),
            reserve_assets=request.facts.get("reserve_assets"),
            reserve_ratio=request.facts.get("reserve_ratio", 1.0),
            uses_algorithmic_mechanism=request.facts.get("uses_algorithmic_mechanism", False),
            issuer_charter_type=request.facts.get("issuer_charter_type", "non_bank_qualified"),
            has_reserve_attestation=request.facts.get("has_reserve_attestation", False),
            attestation_frequency_days=request.facts.get("attestation_frequency_days", 30),
        )
        result = {
            "standard": compliance_result.standard.value,
            "classification": compliance_result.classification.value,
            "requires_sec_registration": compliance_result.requires_sec_registration,
            "genius_act_applicable": compliance_result.genius_act_applicable,
            "sec_jurisdiction": compliance_result.sec_jurisdiction,
            "cftc_jurisdiction": compliance_result.cftc_jurisdiction,
            "compliance_requirements": compliance_result.compliance_requirements,
            "regulatory_risks": compliance_result.regulatory_risks,
            "recommended_actions": compliance_result.recommended_actions,
        }
        if compliance_result.howey_analysis:
            result["howey_analysis"] = {
                "is_security": compliance_result.howey_analysis.is_security,
                "investment_of_money": compliance_result.howey_analysis.investment_of_money,
                "common_enterprise": compliance_result.howey_analysis.common_enterprise,
                "expectation_of_profit": compliance_result.howey_analysis.expectation_of_profit,
                "efforts_of_others": compliance_result.howey_analysis.efforts_of_others,
                "analysis_notes": compliance_result.howey_analysis.analysis_notes,
            }
        if compliance_result.genius_analysis:
            result["genius_analysis"] = {
                "is_compliant_stablecoin": compliance_result.genius_analysis.is_compliant_stablecoin,
                "reserve_requirements_met": compliance_result.genius_analysis.reserve_requirements_met,
                "issuer_requirements": compliance_result.genius_analysis.issuer_requirements,
            }
        audit_trail.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "action": "TOKEN_COMPLIANCE_ANALYSIS",
                "details": {
                    "token_standard": request.token_standard,
                    "classification": compliance_result.classification.value,
                    "is_security": (
                        compliance_result.howey_analysis.is_security if compliance_result.howey_analysis else None
                    ),
                },
            }
        )
        return result
    except Exception as e:
        audit_trail.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "action": "TOKEN_COMPLIANCE_ERROR",
                "details": {"error": str(e)},
            }
        )
        return None


def _assess_protocol_risk(request: NavigateRequest, audit_trail: list[dict]) -> dict | None:
    """Run protocol risk assessment if underlying_chain is provided."""
    try:
        from src.protocol_risk.constants import PROTOCOL_DEFAULTS
        from src.protocol_risk.service import assess_protocol_risk, get_protocol_defaults

        chain_key = request.underlying_chain.lower()
        if chain_key not in PROTOCOL_DEFAULTS:
            return None

        defaults = get_protocol_defaults(chain_key)
        assessment = assess_protocol_risk(protocol_id=chain_key, **defaults)
        result = {
            "protocol_id": assessment.protocol_id,
            "risk_tier": assessment.risk_tier.value,
            "overall_score": assessment.overall_score,
            "consensus_score": assessment.consensus_score,
            "decentralization_score": assessment.decentralization_score,
            "settlement_score": assessment.settlement_score,
            "operational_score": assessment.operational_score,
            "security_score": assessment.security_score,
            "risk_factors": assessment.risk_factors,
            "strengths": assessment.strengths,
            "regulatory_notes": assessment.regulatory_notes,
        }
        audit_trail.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "action": "PROTOCOL_RISK_ASSESSMENT",
                "details": {
                    "protocol": chain_key,
                    "risk_tier": assessment.risk_tier.value,
                    "overall_score": assessment.overall_score,
                },
            }
        )
        return result
    except Exception as e:
        audit_trail.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "action": "PROTOCOL_RISK_ERROR",
                "details": {"error": str(e)},
            }
        )
        return None


def _score_defi_risk(request: NavigateRequest, audit_trail: list[dict]) -> dict | None:
    """Run DeFi risk scoring if defi_protocol is provided."""
    try:
        from src.defi_risk.constants import DEFI_PROTOCOL_DEFAULTS
        from src.defi_risk.schemas import (
            EconomicRisk,
            GovernanceRisk,
            OracleRisk,
            SmartContractRisk,
        )
        from src.defi_risk.service import score_defi_protocol

        protocol_key = request.defi_protocol.lower()
        if protocol_key not in DEFI_PROTOCOL_DEFAULTS:
            return None

        defaults = DEFI_PROTOCOL_DEFAULTS[protocol_key]
        defi_score = score_defi_protocol(
            protocol_id=protocol_key,
            category=defaults["category"],
            smart_contract=SmartContractRisk(**defaults["smart_contract"]),
            economic=EconomicRisk(**defaults["economic"]),
            oracle=OracleRisk(**defaults["oracle"]),
            governance=GovernanceRisk(**defaults["governance"]),
        )
        result = {
            "protocol_id": defi_score.protocol_id,
            "category": defi_score.category.value,
            "overall_grade": defi_score.overall_grade.value,
            "overall_score": defi_score.overall_score,
            "smart_contract_grade": defi_score.smart_contract_grade.value,
            "smart_contract_score": defi_score.smart_contract_score,
            "economic_grade": defi_score.economic_grade.value,
            "economic_score": defi_score.economic_score,
            "oracle_grade": defi_score.oracle_grade.value,
            "oracle_score": defi_score.oracle_score,
            "governance_grade": defi_score.governance_grade.value,
            "governance_score": defi_score.governance_score,
            "regulatory_flags": defi_score.regulatory_flags,
            "critical_risks": defi_score.critical_risks,
            "high_risks": defi_score.high_risks,
            "strengths": defi_score.strengths,
        }
        audit_trail.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "action": "DEFI_RISK_SCORING",
                "details": {
                    "protocol": protocol_key,
                    "overall_grade": defi_score.overall_grade.value,
                    "overall_score": defi_score.overall_score,
                },
            }
        )
        return result
    except Exception as e:
        audit_trail.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "action": "DEFI_RISK_ERROR",
                "details": {"error": str(e)},
            }
        )
        return None

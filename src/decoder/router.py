"""Decoder API routes - tiered explanations and counterfactual analysis.

Combines decoder and counterfactual endpoints for:
- Tiered explanations (retail, protocol, institutional, regulator)
- What-if counterfactual analysis
- Scenario comparisons
- LLM-based explanations (from Console)
"""

from __future__ import annotations

import contextlib

from fastapi import APIRouter, HTTPException

from src.config import get_settings
from src.rules.service import DecisionEngine, RuleLoader

from .llm_service import LLMDecoderService
from .schemas import (
    AnalyzeByIdRequest,
    CompareByIdRequest,
    ComparisonMatrix,
    CounterfactualResponse,
    DecoderResponse,
    ExplainByDecisionRequest,
    InlineAnalyzeRequest,
    InlineCompareRequest,
    InlineDecisionRequest,
    LLMDecoderResponse,
    LLMExplainRequest,
    LLMTiersResponse,
    Scenario,
    TemplateInfo,
)
from .service import CounterfactualEngine, DecoderService

# =============================================================================
# Router Setup
# =============================================================================

router = APIRouter(prefix="/decoder", tags=["decoder"])
counterfactual_router = APIRouter(prefix="/counterfactual", tags=["decoder"])


# =============================================================================
# Shared State
# =============================================================================

_loader: RuleLoader | None = None
_engine: DecisionEngine | None = None
_decoder: DecoderService | None = None
_counterfactual: CounterfactualEngine | None = None
_llm_decoder: LLMDecoderService | None = None


def get_loader() -> RuleLoader:
    """Get or create the rule loader instance."""
    global _loader
    if _loader is None:
        settings = get_settings()
        _loader = RuleLoader(settings.rules_dir)
        with contextlib.suppress(FileNotFoundError):
            _loader.load_directory()
    return _loader


def get_engine() -> DecisionEngine:
    """Get or create the decision engine instance."""
    global _engine
    if _engine is None:
        _engine = DecisionEngine(get_loader())
    return _engine


def get_decoder() -> DecoderService:
    """Get or create the decoder service instance."""
    global _decoder
    if _decoder is None:
        _decoder = DecoderService()
    return _decoder


def get_counterfactual() -> CounterfactualEngine:
    """Get or create the counterfactual engine instance."""
    global _counterfactual
    if _counterfactual is None:
        _counterfactual = CounterfactualEngine(decision_engine=get_engine())
    return _counterfactual


def get_llm_decoder() -> LLMDecoderService:
    """Get or create the LLM decoder service instance."""
    global _llm_decoder
    if _llm_decoder is None:
        _llm_decoder = LLMDecoderService()
    return _llm_decoder


# =============================================================================
# Decoder Endpoints
# =============================================================================


@router.post("/explain", response_model=DecoderResponse)
async def explain_decision(request: ExplainByDecisionRequest) -> DecoderResponse:
    """Generate tiered explanation for an existing decision."""
    decoder = get_decoder()
    return decoder.explain_by_id(
        decision_id=request.decision_id,
        tier=request.tier,
        include_citations=request.include_citations,
    )


@router.post("/explain/inline", response_model=DecoderResponse)
async def explain_inline(request: InlineDecisionRequest) -> DecoderResponse:
    """Evaluate a scenario and generate explanation in one call."""
    from src.ontology.scenario import Scenario as OntologyScenario

    engine = get_engine()
    decoder = get_decoder()

    # Build scenario
    scenario = OntologyScenario(
        instrument_type=request.instrument_type,
        activity=request.activity,
        jurisdiction=request.jurisdiction,
        authorized=request.authorized,
        actor_type=request.actor_type,
        issuer_type=request.issuer_type,
        is_credit_institution=request.is_credit_institution,
        is_authorized_institution=request.is_authorized_institution,
        reference_asset=request.reference_asset,
        is_significant=request.is_significant,
        reserve_value_eur=request.reserve_value_eur,
        extra=request.extra,
    )

    # Evaluate
    if request.rule_id:
        result = engine.evaluate(scenario, request.rule_id)
    else:
        results = engine.evaluate_all(scenario)
        if not results:
            raise HTTPException(
                status_code=404,
                detail="No applicable rules found for this scenario",
            )
        result = next((r for r in results if r.applicable), results[0])

    # Generate explanation
    return decoder.explain(
        decision=result,
        tier=request.tier,
        include_citations=request.include_citations,
    )


@router.get("/templates")
async def list_templates() -> list[TemplateInfo]:
    """List available explanation templates."""
    decoder = get_decoder()
    templates = decoder.templates.list_templates()

    return [
        TemplateInfo(
            id=t.id,
            name=t.name,
            version=t.version,
            frameworks=t.frameworks,
            activity_types=t.activity_types,
            outcome=t.outcome,
        )
        for t in templates
    ]


@router.get("/templates/{template_id}")
async def get_template(template_id: str) -> dict:
    """Get details of a specific template."""
    decoder = get_decoder()
    template = decoder.templates.get(template_id)

    if not template:
        raise HTTPException(
            status_code=404,
            detail=f"Template not found: {template_id}",
        )

    return {
        "id": template.id,
        "name": template.name,
        "version": template.version,
        "frameworks": template.frameworks,
        "activity_types": template.activity_types,
        "outcome": template.outcome,
        "tiers": {
            tier.value: [{"type": s.type, "template": s.template, "llm_enhance": s.llm_enhance} for s in sections]
            for tier, sections in template.tiers.items()
        },
        "variables": [{"name": v.name, "source": v.source, "required": v.required} for v in template.variables],
    }


@router.get("/tiers")
async def list_tiers() -> list[dict]:
    """List available explanation tiers."""
    return [
        {
            "id": "retail",
            "name": "Retail",
            "description": "Plain language, 2-3 sentences for end users",
        },
        {
            "id": "protocol",
            "name": "Protocol",
            "description": "Technical rationale for smart contract integration",
        },
        {
            "id": "institutional",
            "name": "Institutional",
            "description": "Full compliance report for institutions",
        },
        {
            "id": "regulator",
            "name": "Regulator",
            "description": "Complete legal analysis for regulatory review",
        },
    ]


# =============================================================================
# LLM Decoder Endpoints (from Console)
# =============================================================================


@router.post("/llm/explain", response_model=LLMDecoderResponse)
async def llm_explain(request: LLMExplainRequest) -> LLMDecoderResponse:
    """Generate an LLM-based explanation for a risk assessment."""
    llm_decoder = get_llm_decoder()
    return llm_decoder.explain(request)


@router.get("/llm/tiers", response_model=LLMTiersResponse)
async def llm_list_tiers() -> LLMTiersResponse:
    """List available LLM explanation tiers."""
    llm_decoder = get_llm_decoder()
    return llm_decoder.get_available_tiers()


@router.get("/llm/health")
async def llm_decoder_health() -> dict:
    """Check LLM decoder health and API key status."""
    llm_decoder = get_llm_decoder()
    return llm_decoder.get_health()


# =============================================================================
# Counterfactual Endpoints
# =============================================================================


@router.post("/counterfactual/analyze", response_model=CounterfactualResponse)
async def analyze_counterfactual(request: AnalyzeByIdRequest) -> CounterfactualResponse:
    """Analyze a counterfactual scenario for an existing decision."""
    cf_engine = get_counterfactual()

    scenario = Scenario(
        type=request.scenario.type,
        name=request.scenario.name,
        parameters=request.scenario.parameters,
    )

    return cf_engine.analyze_by_id(
        request=type(
            "CounterfactualRequest",
            (),
            {
                "baseline_decision_id": request.baseline_decision_id,
                "scenario": scenario,
                "include_explanation": request.include_explanation,
                "explanation_tier": request.explanation_tier,
            },
        )()
    )


@router.post("/counterfactual/analyze/inline", response_model=CounterfactualResponse)
async def analyze_inline(request: InlineAnalyzeRequest) -> CounterfactualResponse:
    """Evaluate baseline and analyze counterfactual in one call."""
    from src.ontology.scenario import Scenario as OntologyScenario

    engine = get_engine()
    cf_engine = get_counterfactual()

    # Build baseline scenario
    baseline_scenario = OntologyScenario(
        instrument_type=request.instrument_type,
        activity=request.activity,
        jurisdiction=request.jurisdiction,
        authorized=request.authorized,
        actor_type=request.actor_type,
        issuer_type=request.issuer_type,
        is_credit_institution=request.is_credit_institution,
        is_authorized_institution=request.is_authorized_institution,
        reference_asset=request.reference_asset,
        is_significant=request.is_significant,
        reserve_value_eur=request.reserve_value_eur,
        extra=request.extra,
    )

    # Evaluate baseline
    if request.rule_id:
        baseline_result = engine.evaluate(baseline_scenario, request.rule_id)
    else:
        results = engine.evaluate_all(baseline_scenario)
        if not results:
            raise HTTPException(
                status_code=404,
                detail="No applicable rules found for baseline scenario",
            )
        baseline_result = next((r for r in results if r.applicable), results[0])

    # Build counterfactual scenario
    cf_scenario = Scenario(
        type=request.scenario.type,
        name=request.scenario.name,
        parameters=request.scenario.parameters,
    )

    # Analyze counterfactual
    return cf_engine.analyze(
        baseline_decision=baseline_result,
        scenario=cf_scenario,
        include_explanation=request.include_explanation,
        explanation_tier=request.explanation_tier,
    )


@router.post("/counterfactual/compare", response_model=ComparisonMatrix)
async def compare_scenarios(request: CompareByIdRequest) -> ComparisonMatrix:
    """Compare multiple counterfactual scenarios for an existing decision."""
    cf_engine = get_counterfactual()

    scenarios = [
        Scenario(
            type=s.type,
            name=s.name,
            parameters=s.parameters,
        )
        for s in request.scenarios
    ]

    return cf_engine.compare_by_id(
        request=type(
            "ComparisonRequest",
            (),
            {
                "baseline_decision_id": request.baseline_decision_id,
                "scenarios": scenarios,
            },
        )()
    )


@router.post("/counterfactual/compare/inline", response_model=ComparisonMatrix)
async def compare_inline(request: InlineCompareRequest) -> ComparisonMatrix:
    """Evaluate baseline and compare multiple scenarios in one call."""
    from src.ontology.scenario import Scenario as OntologyScenario

    engine = get_engine()
    cf_engine = get_counterfactual()

    # Build baseline scenario
    baseline_scenario = OntologyScenario(
        instrument_type=request.instrument_type,
        activity=request.activity,
        jurisdiction=request.jurisdiction,
        authorized=request.authorized,
        actor_type=request.actor_type,
        issuer_type=request.issuer_type,
        is_credit_institution=request.is_credit_institution,
        is_authorized_institution=request.is_authorized_institution,
        reference_asset=request.reference_asset,
        is_significant=request.is_significant,
        reserve_value_eur=request.reserve_value_eur,
        extra=request.extra,
    )

    # Evaluate baseline
    if request.rule_id:
        baseline_result = engine.evaluate(baseline_scenario, request.rule_id)
    else:
        results = engine.evaluate_all(baseline_scenario)
        if not results:
            raise HTTPException(
                status_code=404,
                detail="No applicable rules found for baseline scenario",
            )
        baseline_result = next((r for r in results if r.applicable), results[0])

    # Build counterfactual scenarios
    cf_scenarios = [
        Scenario(
            type=s.type,
            name=s.name,
            parameters=s.parameters,
        )
        for s in request.scenarios
    ]

    # Compare scenarios
    return cf_engine.compare(
        baseline_decision=baseline_result,
        scenarios=cf_scenarios,
    )


@counterfactual_router.get("/scenario-types")
async def list_scenario_types() -> list[dict]:
    """List available counterfactual scenario types."""
    return [
        {
            "id": "jurisdiction_change",
            "name": "Jurisdiction Change",
            "description": "What if the activity was in a different jurisdiction?",
            "parameters": ["from_jurisdiction", "to_jurisdiction"],
        },
        {
            "id": "entity_change",
            "name": "Entity Type Change",
            "description": "What if the entity type was different?",
            "parameters": ["from_entity_type", "to_entity_type"],
        },
        {
            "id": "activity_restructure",
            "name": "Activity Restructure",
            "description": "What if the activity was structured differently?",
            "parameters": ["new_activity", "modifications"],
        },
        {
            "id": "threshold",
            "name": "Threshold Change",
            "description": "What if certain thresholds changed?",
            "parameters": ["threshold_type", "new_value"],
        },
        {
            "id": "temporal",
            "name": "Temporal Change",
            "description": "What if evaluated at a different time?",
            "parameters": ["effective_date"],
        },
        {
            "id": "protocol_change",
            "name": "Protocol Change",
            "description": "What if using a different protocol/technology?",
            "parameters": ["protocol", "technical_features"],
        },
        {
            "id": "regulatory_change",
            "name": "Regulatory Change",
            "description": "What if regulations changed?",
            "parameters": ["change_type", "new_requirements"],
        },
    ]

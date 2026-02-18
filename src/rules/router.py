"""Routes for regulatory decisions and rule inspection."""

import json

from fastapi import APIRouter, HTTPException, Query

from src.ontology.scenario import Scenario
from src.rules.dependencies import get_engine, get_loader, reset_loader
from src.rules.schemas import (
    DecideRequest,
    DecideResponse,
    DecisionResponse,
    ObligationResponse,
    RuleDetailResponse,
    RuleEventListResponse,
    RuleEventResponse,
    RuleInfo,
    RulesListResponse,
    RuleVersionDetailResponse,
    RuleVersionListResponse,
    RuleVersionResponse,
    TraceStepResponse,
)

# =============================================================================
# Decide Router
# =============================================================================

decide_router = APIRouter(prefix="/decide", tags=["Decisions"])


@decide_router.post("", response_model=DecideResponse)
async def evaluate_scenario(request: DecideRequest) -> DecideResponse:
    """Evaluate a scenario against regulatory rules."""
    engine = get_engine()

    scenario = Scenario(
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

    if request.rule_id:
        result = engine.evaluate(scenario, request.rule_id)
        results = [result]
    else:
        results = engine.evaluate_all(scenario)

    responses = []
    for result in results:
        trace_steps = [
            TraceStepResponse(
                node=step.node,
                condition=step.condition,
                result=step.result,
                value_checked=step.value_checked,
            )
            for step in result.trace
        ]

        obligations = [
            ObligationResponse(
                id=obl.id,
                description=obl.description,
                source=obl.source,
                deadline=obl.deadline,
            )
            for obl in result.obligations
        ]

        responses.append(
            DecisionResponse(
                rule_id=result.rule_id,
                applicable=result.applicable,
                decision=result.decision,
                trace=trace_steps,
                obligations=obligations,
                source=result.source,
                notes=result.notes,
            )
        )

    summary = _generate_summary(responses)
    return DecideResponse(results=responses, summary=summary)


def _generate_summary(responses: list[DecisionResponse]) -> str | None:
    """Generate a summary of the decision results."""
    if not responses:
        return "No applicable rules found for this scenario."

    applicable = [r for r in responses if r.applicable]
    if not applicable:
        return "Scenario does not match any rule conditions."

    all_obligations = []
    for r in applicable:
        all_obligations.extend(r.obligations)

    decisions = [r.decision for r in applicable if r.decision]
    unique_decisions = list(set(decisions))

    summary_parts = [f"Evaluated {len(applicable)} applicable rule(s)."]

    if unique_decisions:
        summary_parts.append(f"Outcomes: {', '.join(unique_decisions)}.")

    if all_obligations:
        summary_parts.append(f"{len(all_obligations)} obligation(s) triggered.")

    return " ".join(summary_parts)


@decide_router.post("/reload")
async def reload_rules() -> dict:
    """Reload rules from disk."""
    reset_loader()

    loader = get_loader()
    rules = loader.get_all_rules()

    return {
        "status": "reloaded",
        "rules_loaded": len(rules),
    }


# =============================================================================
# Rules Router
# =============================================================================

rules_router = APIRouter(prefix="/rules", tags=["Rules"])


@rules_router.get("", response_model=RulesListResponse)
async def list_rules(tag: str | None = None) -> RulesListResponse:
    """List all available rules. Optionally filter by tag."""
    loader = get_loader()

    rules = loader.get_applicable_rules(tags=[tag]) if tag else loader.get_all_rules()

    rule_infos = []
    for rule in rules:
        source_str = None
        if rule.source:
            parts = [rule.source.document_id]
            if rule.source.article:
                parts.append(f"Art. {rule.source.article}")
            source_str = " ".join(parts)

        rule_infos.append(
            RuleInfo(
                rule_id=rule.rule_id,
                version=rule.version,
                description=rule.description,
                effective_from=rule.effective_from.isoformat() if rule.effective_from else None,
                effective_to=rule.effective_to.isoformat() if rule.effective_to else None,
                tags=rule.tags,
                source=source_str,
            )
        )

    return RulesListResponse(rules=rule_infos, total=len(rule_infos))


@rules_router.get("/{rule_id}", response_model=RuleDetailResponse)
async def get_rule(rule_id: str) -> RuleDetailResponse:
    """Get detailed information about a specific rule."""
    loader = get_loader()
    rule = loader.get_rule(rule_id)

    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")

    applies_if = None
    if rule.applies_if:
        applies_if = rule.applies_if.model_dump(exclude_none=True)

    decision_tree = None
    if rule.decision_tree:
        decision_tree = rule.decision_tree.model_dump(exclude_none=True)

    source = None
    if rule.source:
        source = rule.source.model_dump(exclude_none=True)

    return RuleDetailResponse(
        rule_id=rule.rule_id,
        version=rule.version,
        description=rule.description,
        effective_from=rule.effective_from.isoformat() if rule.effective_from else None,
        effective_to=rule.effective_to.isoformat() if rule.effective_to else None,
        tags=rule.tags,
        source=source,
        applies_if=applies_if,
        decision_tree=decision_tree,
        interpretation_notes=rule.interpretation_notes,
    )


@rules_router.get("/tags/all")
async def list_tags() -> dict:
    """List all unique tags across rules."""
    loader = get_loader()
    rules = loader.get_all_rules()

    tags = set()
    for rule in rules:
        tags.update(rule.tags)

    return {"tags": sorted(tags)}


# =============================================================================
# Version Endpoints (lazy-loaded repos)
# =============================================================================


def _get_version_repo():
    from src.rules.version_repository import RuleVersionRepository

    return RuleVersionRepository()


def _get_event_repo():
    from src.rules.event_repository import RuleEventRepository

    return RuleEventRepository()


@rules_router.get("/{rule_id}/versions", response_model=RuleVersionListResponse)
async def list_versions(rule_id: str, limit: int = Query(100, ge=1, le=1000)) -> RuleVersionListResponse:
    """List all versions of a rule."""
    repo = _get_version_repo()
    versions = repo.get_version_history(rule_id, limit=limit)

    if not versions:
        raise HTTPException(status_code=404, detail=f"No versions found for rule: {rule_id}")

    return RuleVersionListResponse(
        rule_id=rule_id,
        versions=[
            RuleVersionResponse(
                id=v.id,
                rule_id=v.rule_id,
                version=v.version,
                content_hash=v.content_hash,
                effective_from=v.effective_from,
                effective_to=v.effective_to,
                created_at=v.created_at,
                created_by=v.created_by,
                superseded_by=v.superseded_by,
                superseded_at=v.superseded_at,
                jurisdiction_code=v.jurisdiction_code,
                regime_id=v.regime_id,
            )
            for v in versions
        ],
        total=len(versions),
    )


@rules_router.get("/{rule_id}/versions/{version}", response_model=RuleVersionDetailResponse)
async def get_version(rule_id: str, version: int) -> RuleVersionDetailResponse:
    """Get a specific version of a rule."""
    repo = _get_version_repo()
    v = repo.get_version(rule_id, version)

    if not v:
        raise HTTPException(status_code=404, detail=f"Version {version} not found for rule: {rule_id}")

    return RuleVersionDetailResponse(
        id=v.id,
        rule_id=v.rule_id,
        version=v.version,
        content_hash=v.content_hash,
        content_yaml=v.content_yaml,
        content_json=v.content_json,
        effective_from=v.effective_from,
        effective_to=v.effective_to,
        created_at=v.created_at,
        created_by=v.created_by,
        superseded_by=v.superseded_by,
        superseded_at=v.superseded_at,
        jurisdiction_code=v.jurisdiction_code,
        regime_id=v.regime_id,
    )


@rules_router.get("/{rule_id}/at-timestamp", response_model=RuleVersionDetailResponse)
async def get_version_at_timestamp(
    rule_id: str, timestamp: str = Query(..., description="ISO 8601 timestamp")
) -> RuleVersionDetailResponse:
    """Get the version of a rule effective at a specific timestamp."""
    repo = _get_version_repo()
    v = repo.get_version_at_timestamp(rule_id, timestamp)

    if not v:
        raise HTTPException(
            status_code=404,
            detail=f"No version found for rule {rule_id} at timestamp {timestamp}",
        )

    return RuleVersionDetailResponse(
        id=v.id,
        rule_id=v.rule_id,
        version=v.version,
        content_hash=v.content_hash,
        content_yaml=v.content_yaml,
        content_json=v.content_json,
        effective_from=v.effective_from,
        effective_to=v.effective_to,
        created_at=v.created_at,
        created_by=v.created_by,
        superseded_by=v.superseded_by,
        superseded_at=v.superseded_at,
        jurisdiction_code=v.jurisdiction_code,
        regime_id=v.regime_id,
    )


@rules_router.get("/{rule_id}/events", response_model=RuleEventListResponse)
async def list_events(rule_id: str, limit: int = Query(100, ge=1, le=1000)) -> RuleEventListResponse:
    """List all events for a rule."""
    repo = _get_event_repo()
    events = repo.get_events_for_rule(rule_id)
    events = events[:limit]

    return RuleEventListResponse(
        rule_id=rule_id,
        events=[
            RuleEventResponse(
                id=e.id,
                sequence_number=e.sequence_number,
                rule_id=e.rule_id,
                version=e.version,
                event_type=e.event_type,
                event_data=json.loads(e.event_data) if e.event_data else {},
                timestamp=e.timestamp,
                actor=e.actor,
                reason=e.reason,
            )
            for e in events
        ],
        total=len(events),
    )

"""Verification API routes — /verification/* endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from src.rules.service import RuleLoader

from .schemas import VerifyRuleRequest, VerifyRuleResponse
from .service import ConsistencyEngine

verification_router = APIRouter(prefix="/verification", tags=["Verification"])

_engine: ConsistencyEngine | None = None
_loader: RuleLoader | None = None


def _get_engine() -> ConsistencyEngine:
    global _engine
    if _engine is None:
        _engine = ConsistencyEngine()
    return _engine


def _get_loader() -> RuleLoader:
    global _loader
    if _loader is None:
        _loader = RuleLoader()
    return _loader


@verification_router.post("/verify", response_model=VerifyRuleResponse)
async def verify_rule_endpoint(request: VerifyRuleRequest) -> VerifyRuleResponse:
    """Verify consistency of a single rule.

    Runs Tier 0 (structural) and Tier 1 (lexical) checks by default.
    """
    loader = _get_loader()
    rule = loader.get_rule(request.rule_id)

    if rule is None:
        raise HTTPException(status_code=404, detail=f"Rule not found: {request.rule_id}")

    engine = _get_engine()
    result = engine.verify_rule(
        rule=rule,
        source_text=request.source_text,
        tiers=request.tiers,
    )

    return VerifyRuleResponse(
        rule_id=request.rule_id,
        status=result.summary.status.value,
        confidence=result.summary.confidence,
        evidence_count=len(result.evidence),
        evidence=[
            {
                "tier": ev.tier,
                "category": ev.category,
                "label": ev.label,
                "score": ev.score,
                "details": ev.details,
            }
            for ev in result.evidence
        ],
    )


@verification_router.post("/verify-all")
async def verify_all_rules(
    tiers: list[int] = Query(default=[0, 1]),
    save: bool = Query(default=False, description="Save results to rule files"),
) -> dict[str, Any]:
    """Verify all loaded rules."""
    loader = _get_loader()
    engine = _get_engine()
    rules = loader.get_all_rules()

    results = []
    for rule in rules:
        consistency = engine.verify_rule(rule, tiers=tiers)
        results.append(
            {
                "rule_id": rule.rule_id,
                "status": consistency.summary.status.value,
                "confidence": consistency.summary.confidence,
            }
        )
        if save:
            rule.consistency = consistency

    return {
        "total": len(results),
        "verified": sum(1 for r in results if r["status"] == "verified"),
        "needs_review": sum(1 for r in results if r["status"] == "needs_review"),
        "inconsistent": sum(1 for r in results if r["status"] == "inconsistent"),
        "results": results,
    }

"""FastAPI router for Knowledge Engineering workbench.

Provides /ke/* endpoints for rule verification, analytics, drift detection,
human review, and chart visualization. Delegates to KEService.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from src.analytics.utils import is_supertree_available

from .schemas import (
    AnalyticsSummaryResponse,
    ChartDataResponse,
    ChartHtmlResponse,
    DriftReportResponse,
    ErrorPatternResponse,
    EvaluateForTraceRequest,
    HumanReviewRequest,
    HumanReviewResponse,
    ReviewQueueItem,
    VerifyAllResponse,
    VerifyRuleRequest,
    VerifyRuleResponse,
)
from .service import KEService

router = APIRouter(prefix="/ke", tags=["Knowledge Engineering"])


# =============================================================================
# Shared state (lazily initialized)
# =============================================================================

_ke_service: KEService | None = None


def get_ke_service() -> KEService:
    global _ke_service
    if _ke_service is None:
        _ke_service = KEService()
    return _ke_service


# =============================================================================
# Consistency Verification
# =============================================================================


@router.post("/verify", response_model=VerifyRuleResponse)
def verify_rule_endpoint(request: VerifyRuleRequest):
    """Verify consistency of a single rule."""
    svc = get_ke_service()
    result = svc.verify_rule(request.rule_id, source_text=request.source_text, tiers=request.tiers)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Rule not found: {request.rule_id}")
    return VerifyRuleResponse(**result)


@router.post("/verify-all", response_model=VerifyAllResponse)
def verify_all_rules(
    tiers: list[int] = Query(default=[0, 1]),
    save: bool = Query(default=False, description="Save results to rule files"),
):
    """Verify all loaded rules."""
    svc = get_ke_service()
    return VerifyAllResponse(**svc.verify_all_rules(tiers=tiers, save=save))


# =============================================================================
# Analytics
# =============================================================================


@router.get("/analytics/summary", response_model=AnalyticsSummaryResponse)
def get_analytics_summary():
    """Get summary statistics for all rules."""
    svc = get_ke_service()
    return AnalyticsSummaryResponse(**svc.get_analytics_summary())


@router.get("/analytics/patterns", response_model=list[ErrorPatternResponse])
def get_error_patterns(min_affected: int = Query(default=2)):
    """Detect error patterns across rules."""
    svc = get_ke_service()
    patterns = svc.get_error_patterns(min_affected=min_affected)
    return [
        ErrorPatternResponse(
            pattern_id=p.pattern_id,
            category=p.category,
            description=p.description,
            severity=p.severity,
            affected_rule_count=p.affected_rule_count,
            affected_rules=p.affected_rules,
            recommendation=p.recommendation,
        )
        for p in patterns
    ]


@router.get("/analytics/matrix")
def get_error_matrix() -> dict[str, dict[str, int]]:
    """Get error confusion matrix (category x outcome)."""
    svc = get_ke_service()
    return svc.get_error_matrix()


@router.get("/analytics/review-queue", response_model=list[ReviewQueueItem])
def get_review_queue(max_items: int = Query(default=50)):
    """Get prioritized review queue."""
    svc = get_ke_service()
    queue = svc.get_review_queue(max_items=max_items)
    return [
        ReviewQueueItem(
            rule_id=item.rule_id,
            priority=item.priority,
            status=item.status.value,
            confidence=item.confidence,
            issues=item.issues,
        )
        for item in queue
    ]


# =============================================================================
# Drift Detection
# =============================================================================


@router.post("/drift/baseline")
def set_drift_baseline() -> dict:
    """Set current state as drift baseline."""
    svc = get_ke_service()
    return svc.set_drift_baseline()


@router.get("/drift/detect", response_model=DriftReportResponse)
def detect_drift():
    """Detect drift from baseline."""
    svc = get_ke_service()
    report = svc.detect_drift()
    return DriftReportResponse(
        report_id=report.report_id,
        drift_detected=report.drift_detected,
        drift_severity=report.drift_severity,
        degraded_categories=report.degraded_categories,
        improved_categories=report.improved_categories,
        summary=report.summary,
    )


@router.get("/drift/history")
def get_drift_history(window: int = Query(default=10)) -> list[dict]:
    """Get metrics history."""
    svc = get_ke_service()
    history = svc.get_drift_history(window=window)
    return [
        {
            "timestamp": m.timestamp,
            "total_rules": m.total_rules,
            "verified": m.verified_count,
            "avg_confidence": m.avg_confidence,
        }
        for m in history
    ]


@router.get("/drift/authors")
def get_author_comparison() -> dict[str, Any]:
    """Compare consistency metrics by author."""
    svc = get_ke_service()
    return svc.get_author_comparison()


# =============================================================================
# Rule Context
# =============================================================================


@router.get("/context/{rule_id}")
def get_rule_context(rule_id: str) -> dict[str, Any]:
    """Get source context for a rule."""
    svc = get_ke_service()
    result = svc.get_rule_context(rule_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")
    return result


@router.get("/related/{rule_id}")
def get_related_rules(rule_id: str, top_k: int = Query(default=5)) -> list[dict]:
    """Get rules related to a given rule."""
    svc = get_ke_service()
    result = svc.get_related_rules(rule_id, top_k=top_k)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")
    return result


# =============================================================================
# Human Review
# =============================================================================


@router.post("/rules/{rule_id}/review", response_model=HumanReviewResponse)
def submit_human_review(rule_id: str, request: HumanReviewRequest):
    """Submit a human review (Tier 4) for a rule."""
    if request.label not in ("consistent", "inconsistent", "unknown"):
        raise HTTPException(
            status_code=400,
            detail="Invalid label. Must be: consistent, inconsistent, unknown",
        )
    svc = get_ke_service()
    result = svc.submit_human_review(rule_id, request.label, request.notes, request.reviewer_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")
    return HumanReviewResponse(**result)


@router.get("/rules/{rule_id}/reviews")
def get_rule_reviews(rule_id: str) -> list[dict]:
    """Get all human reviews for a rule."""
    svc = get_ke_service()
    result = svc.get_rule_reviews(rule_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")
    return result


# =============================================================================
# Chart Visualization
# =============================================================================


@router.get("/charts/supertree-status")
def get_supertree_status() -> dict:
    """Check if Supertree visualization is available."""
    svc = get_ke_service()
    return svc.get_supertree_status()


@router.get("/charts/rulebook-outline", response_model=ChartDataResponse)
def get_rulebook_outline_chart():
    """Get rulebook outline tree data."""
    svc = get_ke_service()
    return ChartDataResponse(
        chart_type="rulebook_outline",
        data=svc.get_rulebook_outline(),
        supertree_available=is_supertree_available(),
    )


@router.get("/charts/rulebook-outline/html", response_model=ChartHtmlResponse)
def get_rulebook_outline_html():
    """Get rulebook outline as rendered HTML."""
    svc = get_ke_service()
    return ChartHtmlResponse(
        chart_type="rulebook_outline",
        html=svc.render_rulebook_outline(),
        supertree_available=is_supertree_available(),
    )


@router.get("/charts/ontology", response_model=ChartDataResponse)
def get_ontology_chart():
    """Get ontology tree data."""
    svc = get_ke_service()
    return ChartDataResponse(
        chart_type="ontology",
        data=svc.get_ontology_tree(),
        supertree_available=is_supertree_available(),
    )


@router.get("/charts/ontology/html", response_model=ChartHtmlResponse)
def get_ontology_html():
    """Get ontology tree as rendered HTML."""
    svc = get_ke_service()
    return ChartHtmlResponse(
        chart_type="ontology",
        html=svc.render_ontology_tree(),
        supertree_available=is_supertree_available(),
    )


@router.get("/charts/corpus-links", response_model=ChartDataResponse)
def get_corpus_links_chart():
    """Get corpus-to-rule links tree data."""
    svc = get_ke_service()
    return ChartDataResponse(
        chart_type="corpus_links",
        data=svc.get_corpus_links(),
        supertree_available=is_supertree_available(),
    )


@router.get("/charts/corpus-links/html", response_model=ChartHtmlResponse)
def get_corpus_links_html():
    """Get corpus-to-rule links as rendered HTML."""
    svc = get_ke_service()
    return ChartHtmlResponse(
        chart_type="corpus_links",
        html=svc.render_corpus_links(),
        supertree_available=is_supertree_available(),
    )


@router.get("/charts/decision-tree/{rule_id}", response_model=ChartDataResponse)
def get_decision_tree_chart(rule_id: str):
    """Get decision tree structure for a rule."""
    svc = get_ke_service()
    result = svc.get_decision_tree(rule_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")
    if isinstance(result, dict) and result.get("error") == "no_decision_tree":
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} has no decision tree")
    return ChartDataResponse(
        chart_type="decision_tree",
        data=result or {},
        supertree_available=is_supertree_available(),
    )


@router.post("/charts/decision-trace/{rule_id}", response_model=ChartDataResponse)
def get_decision_trace_chart(rule_id: str, request: EvaluateForTraceRequest):
    """Evaluate a rule and return decision trace tree data."""
    svc = get_ke_service()
    result = svc.get_decision_trace(rule_id, request.scenario)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")
    return ChartDataResponse(
        chart_type="decision_trace",
        data=result,
        supertree_available=is_supertree_available(),
    )


@router.post("/charts/decision-trace/{rule_id}/html", response_model=ChartHtmlResponse)
def get_decision_trace_html(rule_id: str, request: EvaluateForTraceRequest):
    """Evaluate a rule and return decision trace as HTML."""
    svc = get_ke_service()
    html = svc.render_decision_trace(rule_id, request.scenario)
    if html is None:
        raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")
    return ChartHtmlResponse(
        chart_type="decision_trace",
        html=html,
        supertree_available=is_supertree_available(),
    )

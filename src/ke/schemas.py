"""KE-specific request/response schemas.

Models here are unique to the Knowledge Engineering workbench.
Domain-level schemas (rules, verification, analytics) live in their own domains.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from src.models import CustomBaseModel

# =============================================================================
# Verification
# =============================================================================


class VerifyRuleRequest(CustomBaseModel):
    """Request to verify a rule."""

    rule_id: str
    source_text: str | None = None
    tiers: list[int] = Field(default=[0, 1])


class VerifyRuleResponse(CustomBaseModel):
    """Response from rule verification."""

    rule_id: str
    status: str
    confidence: float
    evidence_count: int
    evidence: list[dict[str, Any]]


class VerifyAllResponse(CustomBaseModel):
    """Response from verifying all rules."""

    total: int
    verified: int
    needs_review: int
    inconsistent: int
    results: list[dict[str, Any]]


# =============================================================================
# Analytics
# =============================================================================


class AnalyticsSummaryResponse(CustomBaseModel):
    """Analytics summary response."""

    total_rules: int
    verified: int
    needs_review: int
    inconsistent: int
    unverified: int
    verification_rate: float
    average_score: float
    timestamp: str


class ReviewQueueItem(CustomBaseModel):
    """Item in review queue."""

    rule_id: str
    priority: float
    status: str
    confidence: float
    issues: list[str]


class ErrorPatternResponse(CustomBaseModel):
    """Error pattern response."""

    pattern_id: str
    category: str
    description: str
    severity: str
    affected_rule_count: int
    affected_rules: list[str]
    recommendation: str


# =============================================================================
# Drift Detection
# =============================================================================


class DriftReportResponse(CustomBaseModel):
    """Drift detection report."""

    report_id: str
    drift_detected: bool
    drift_severity: str
    degraded_categories: list[str]
    improved_categories: list[str]
    summary: str


# =============================================================================
# Human Review
# =============================================================================


class HumanReviewRequest(CustomBaseModel):
    """Request to submit human review."""

    label: str = Field(..., description="Review decision: consistent, inconsistent, unknown")
    notes: str = Field(..., description="Reviewer notes explaining the decision")
    reviewer_id: str = Field(..., description="Identifier of the human reviewer")


class HumanReviewResponse(CustomBaseModel):
    """Response from human review submission."""

    rule_id: str
    status: str
    confidence: float
    review_tier: int = 4
    reviewer_id: str
    message: str


# =============================================================================
# Charts
# =============================================================================


class ChartDataResponse(CustomBaseModel):
    """Response containing tree data for visualization."""

    chart_type: str
    data: dict[str, Any]
    supertree_available: bool


class ChartHtmlResponse(CustomBaseModel):
    """Response containing rendered HTML chart."""

    chart_type: str
    html: str
    supertree_available: bool


class EvaluateForTraceRequest(CustomBaseModel):
    """Request to evaluate a rule and get decision trace."""

    scenario: dict[str, Any] = Field(..., description="Scenario attributes as key-value pairs")

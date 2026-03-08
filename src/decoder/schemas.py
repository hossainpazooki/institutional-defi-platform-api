"""Pydantic schemas for decoder service - tiered explanations and counterfactual analysis."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field

from src.models import CustomBaseModel

# =============================================================================
# Enums
# =============================================================================


class ExplanationTier(StrEnum):
    """Audience tier for explanations."""

    RETAIL = "retail"  # Plain language, 2-3 sentences
    PROTOCOL = "protocol"  # Technical rationale
    INSTITUTIONAL = "institutional"  # Full compliance report
    REGULATOR = "regulator"  # Complete legal analysis


class ScenarioType(StrEnum):
    """Type of counterfactual scenario."""

    JURISDICTION_CHANGE = "jurisdiction_change"
    ENTITY_CHANGE = "entity_change"
    ACTIVITY_RESTRUCTURE = "activity_restructure"
    THRESHOLD = "threshold"
    TEMPORAL = "temporal"
    PROTOCOL_CHANGE = "protocol_change"
    REGULATORY_CHANGE = "regulatory_change"


# =============================================================================
# Citation Models
# =============================================================================


class Citation(CustomBaseModel):
    """A regulatory citation with source reference."""

    id: str = Field(default_factory=lambda: f"cit_{uuid.uuid4().hex[:8]}")
    framework: str  # "MiCA", "FCA", "SEC", etc.
    reference: str  # "Article 3(1)(5)"
    full_reference: str  # "Regulation (EU) 2023/1114, Article 3(1)(5)"
    text: str  # Relevant excerpt
    url: str | None = None
    effective_date: str | None = None
    relevance: Literal["primary", "supporting", "contextual"] = "supporting"
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)


class LLMCitation(CustomBaseModel):
    """A citation anchoring part of an LLM explanation to a data source."""

    source: str  # e.g., "protocol_risk.finality_score"
    text: str  # The cited text
    value: Any  # The actual value
    rule_id: str | None = None  # If from a rule


# =============================================================================
# Explanation Models
# =============================================================================


class Explanation(CustomBaseModel):
    """Structured explanation content."""

    headline: str
    body: str
    conditions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ExplanationSummary(CustomBaseModel):
    """Summary metadata for an explanation."""

    status: str  # "APPROVED", "CONDITIONAL", "DENIED", etc.
    confidence: float = Field(ge=0.0, le=1.0)
    # Droit pattern: 'grounded' = from rule traversal, 'inferred' = LLM reasoning
    confidence_level: Literal["grounded", "inferred"] = "grounded"
    primary_framework: str
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM"


class AuditInfo(CustomBaseModel):
    """Audit information for traceability."""

    trace_id: str | None = None
    rules_evaluated: int = 0
    processing_time_ms: int = 0
    template_id: str | None = None
    model_version: str = "decoder-v1.0"


# =============================================================================
# Decoder Request/Response
# =============================================================================


class DecoderRequest(CustomBaseModel):
    """Request to decode/explain a decision."""

    decision_id: str
    tier: ExplanationTier = ExplanationTier.INSTITUTIONAL
    format: Literal["structured", "markdown", "plain"] = "structured"
    include_citations: bool = True
    include_counterfactuals: bool = False
    language: str = "en"


class DecoderResponse(CustomBaseModel):
    """Response with explanation and citations."""

    explanation_id: str = Field(default_factory=lambda: f"exp_{uuid.uuid4().hex[:8]}")
    decision_id: str
    tier: ExplanationTier
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    summary: ExplanationSummary
    explanation: Explanation
    citations: list[Citation] = Field(default_factory=list)
    audit: AuditInfo = Field(default_factory=AuditInfo)


# =============================================================================
# LLM Decoder Request/Response (from Console)
# =============================================================================


class LLMExplainRequest(CustomBaseModel):
    """Request for LLM-based explanation generation."""

    scenario: str
    results: dict[str, Any]
    tier: str = "anchored"  # "canonical", "anchored", "guided", "exploratory"
    context: dict[str, Any] | None = None


class LLMDecoderResponse(CustomBaseModel):
    """Response from the LLM decoder."""

    decision: str  # The canonical decision
    confidence: float  # 0-1 confidence
    explanation: str  # LLM-generated explanation
    citations: list[LLMCitation]  # Anchored citations
    tier: str  # "canonical", "anchored", "guided", "exploratory"
    generated_at: datetime
    model: str  # Claude model used


class LLMTierInfo(CustomBaseModel):
    """Description of an LLM explanation tier."""

    id: str
    name: str
    description: str
    requires_llm: bool


class LLMTiersResponse(CustomBaseModel):
    """Response model for listing LLM explanation tiers."""

    tiers: list[LLMTierInfo]


# =============================================================================
# Counterfactual Models
# =============================================================================


class Scenario(CustomBaseModel):
    """A counterfactual scenario to evaluate."""

    type: ScenarioType
    name: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class OutcomeSummary(CustomBaseModel):
    """Summary of a compliance outcome."""

    status: str  # "APPROVED", "CONDITIONAL", "DENIED"
    framework: str
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM"
    conditions: list[str] = Field(default_factory=list)


class DeltaAnalysis(CustomBaseModel):
    """Analysis of differences between baseline and counterfactual."""

    status_changed: bool = False
    status_from: str = ""
    status_to: str = ""

    framework_changed: bool = False
    frameworks_added: list[str] = Field(default_factory=list)
    frameworks_removed: list[str] = Field(default_factory=list)

    risk_delta: int = Field(default=0, ge=-2, le=2)  # -2 to +2
    risk_factors_added: list[str] = Field(default_factory=list)
    risk_factors_removed: list[str] = Field(default_factory=list)

    new_requirements: list[str] = Field(default_factory=list)
    removed_requirements: list[str] = Field(default_factory=list)
    modified_requirements: list[dict[str, str]] = Field(default_factory=list)

    # Quantitative impacts
    estimated_cost_delta: float | None = None
    estimated_time_delta: int | None = None  # days
    position_limit_delta: float | None = None


class CounterfactualExplanation(CustomBaseModel):
    """Explanation of counterfactual differences."""

    summary: str
    key_differences: list[dict[str, str]] = Field(default_factory=list)


class CounterfactualRequest(CustomBaseModel):
    """Request for counterfactual analysis."""

    baseline_decision_id: str
    scenario: Scenario
    include_explanation: bool = True
    explanation_tier: ExplanationTier = ExplanationTier.INSTITUTIONAL


class CounterfactualResponse(CustomBaseModel):
    """Response with counterfactual analysis."""

    counterfactual_id: str = Field(default_factory=lambda: f"cf_{uuid.uuid4().hex[:8]}")
    baseline_decision_id: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    scenario_applied: Scenario
    baseline_outcome: OutcomeSummary
    counterfactual_outcome: OutcomeSummary
    delta: DeltaAnalysis

    explanation: CounterfactualExplanation | None = None
    citations: list[Citation] = Field(default_factory=list)


# =============================================================================
# Comparison Matrix (Multi-scenario)
# =============================================================================


class ComparisonRequest(CustomBaseModel):
    """Request to compare multiple scenarios."""

    baseline_decision_id: str
    scenarios: list[Scenario]
    comparison_format: Literal["matrix", "list"] = "matrix"


class MatrixInsight(CustomBaseModel):
    """An insight derived from comparison analysis."""

    type: Literal["recommendation", "warning", "opportunity"]
    text: str


class ComparisonMatrix(CustomBaseModel):
    """Multi-scenario comparison result."""

    comparison_id: str = Field(default_factory=lambda: f"cmp_{uuid.uuid4().hex[:8]}")
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    baseline: OutcomeSummary
    scenarios: list[Scenario] = Field(default_factory=list)
    results: list[CounterfactualResponse] = Field(default_factory=list)

    matrix: dict[str, list[str]] = Field(default_factory=dict)
    insights: list[MatrixInsight] = Field(default_factory=list)


# =============================================================================
# Template Models
# =============================================================================


class TemplateVariable(CustomBaseModel):
    """A variable slot in a template."""

    name: str
    source: Literal["decision", "context", "rag", "computed"]
    required: bool = True
    default: str | None = None


class CitationSlot(CustomBaseModel):
    """A citation slot in a template."""

    slot_id: str
    framework: str
    article_pattern: str


class TemplateSection(CustomBaseModel):
    """A section within a template."""

    type: Literal["headline", "body", "conditions", "warnings", "citations"]
    template: str  # Handlebars-style template
    llm_enhance: bool = False


class ExplanationTemplate(CustomBaseModel):
    """Template for generating tiered explanations."""

    id: str
    name: str
    version: str = "1.0"

    # Matching criteria
    activity_types: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    outcome: Literal["compliant", "non_compliant", "conditional"]

    # Template content per tier
    tiers: dict[ExplanationTier, list[TemplateSection]] = Field(default_factory=dict)

    # Variable definitions
    variables: list[TemplateVariable] = Field(default_factory=list)
    citation_slots: list[CitationSlot] = Field(default_factory=list)


# =============================================================================
# Router Request Models
# =============================================================================


class TemplateInfo(CustomBaseModel):
    """Template summary for listing."""

    id: str
    name: str
    version: str
    frameworks: list[str]
    activity_types: list[str]
    outcome: str


class ExplainByDecisionRequest(CustomBaseModel):
    """Request to explain an existing decision result."""

    decision_id: str
    tier: ExplanationTier = ExplanationTier.INSTITUTIONAL
    include_citations: bool = True


class InlineDecisionRequest(CustomBaseModel):
    """Request with inline scenario for immediate evaluation and explanation."""

    # Scenario fields
    instrument_type: str | None = None
    activity: str | None = None
    jurisdiction: str | None = None
    authorized: bool | None = None
    actor_type: str | None = None
    issuer_type: str | None = None
    is_credit_institution: bool | None = None
    is_authorized_institution: bool | None = None
    reference_asset: str | None = None
    is_significant: bool | None = None
    reserve_value_eur: float | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    # Decoder options
    rule_id: str | None = None
    tier: ExplanationTier = ExplanationTier.INSTITUTIONAL
    include_citations: bool = True


class ScenarioRequest(CustomBaseModel):
    """A counterfactual scenario definition."""

    type: ScenarioType
    name: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class AnalyzeByIdRequest(CustomBaseModel):
    """Request to analyze counterfactual for existing decision."""

    baseline_decision_id: str
    scenario: ScenarioRequest
    include_explanation: bool = True
    explanation_tier: ExplanationTier = ExplanationTier.INSTITUTIONAL


class InlineAnalyzeRequest(CustomBaseModel):
    """Request with inline scenario for immediate counterfactual analysis."""

    # Baseline scenario fields
    instrument_type: str | None = None
    activity: str | None = None
    jurisdiction: str | None = None
    authorized: bool | None = None
    actor_type: str | None = None
    issuer_type: str | None = None
    is_credit_institution: bool | None = None
    is_authorized_institution: bool | None = None
    reference_asset: str | None = None
    is_significant: bool | None = None
    reserve_value_eur: float | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    # Evaluation options
    rule_id: str | None = None

    # Counterfactual scenario
    scenario: ScenarioRequest

    # Options
    include_explanation: bool = True
    explanation_tier: ExplanationTier = ExplanationTier.INSTITUTIONAL


class CompareByIdRequest(CustomBaseModel):
    """Request to compare multiple scenarios for existing decision."""

    baseline_decision_id: str
    scenarios: list[ScenarioRequest]


class InlineCompareRequest(CustomBaseModel):
    """Request with inline scenario for multi-scenario comparison."""

    # Baseline scenario fields
    instrument_type: str | None = None
    activity: str | None = None
    jurisdiction: str | None = None
    authorized: bool | None = None
    actor_type: str | None = None
    issuer_type: str | None = None
    is_credit_institution: bool | None = None
    is_authorized_institution: bool | None = None
    reference_asset: str | None = None
    is_significant: bool | None = None
    reserve_value_eur: float | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    # Evaluation options
    rule_id: str | None = None

    # Counterfactual scenarios
    scenarios: list[ScenarioRequest]

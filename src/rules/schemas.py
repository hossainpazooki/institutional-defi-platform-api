"""Pydantic models for rules domain API requests and responses."""

from typing import Any

from pydantic import BaseModel, Field

# =============================================================================
# Decision Models
# =============================================================================


class DecideRequest(BaseModel):
    """Request for regulatory decision."""

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
    rule_id: str | None = Field(None, description="Evaluate specific rule only")


class TraceStepResponse(BaseModel):
    """A step in the decision trace."""

    node: str
    condition: str
    result: bool
    value_checked: Any = None


class ObligationResponse(BaseModel):
    """An obligation from a decision."""

    id: str
    description: str | None = None
    source: str | None = None
    deadline: str | None = None


class DecisionResponse(BaseModel):
    """Response for a single rule evaluation."""

    rule_id: str
    applicable: bool
    decision: str | None
    trace: list[TraceStepResponse]
    obligations: list[ObligationResponse]
    source: str | None = None
    notes: str | None = None


class DecideResponse(BaseModel):
    """Response for regulatory decision (may include multiple rules)."""

    results: list[DecisionResponse]
    summary: str | None = Field(None, description="Summary of overall outcome")


# =============================================================================
# Rules Models
# =============================================================================


class RuleInfo(BaseModel):
    """Summary information about a rule."""

    rule_id: str
    version: str
    description: str | None
    effective_from: str | None
    effective_to: str | None
    tags: list[str]
    source: str | None


class RulesListResponse(BaseModel):
    """Response listing available rules."""

    rules: list[RuleInfo]
    total: int


class RuleDetailResponse(BaseModel):
    """Detailed rule information."""

    rule_id: str
    version: str
    description: str | None
    effective_from: str | None
    effective_to: str | None
    tags: list[str]
    source: dict[str, Any] | None
    applies_if: dict[str, Any] | None
    decision_tree: dict[str, Any] | None
    interpretation_notes: str | None


# =============================================================================
# Version Models
# =============================================================================


class RuleVersionResponse(BaseModel):
    """A single rule version snapshot."""

    id: str
    rule_id: str
    version: int
    content_hash: str
    effective_from: str | None
    effective_to: str | None
    created_at: str
    created_by: str | None
    superseded_by: int | None
    superseded_at: str | None
    jurisdiction_code: str | None
    regime_id: str | None


class RuleVersionListResponse(BaseModel):
    """Response listing rule versions."""

    rule_id: str
    versions: list[RuleVersionResponse]
    total: int


class RuleVersionDetailResponse(RuleVersionResponse):
    """Detailed version with content."""

    content_yaml: str
    content_json: str | None


class RuleEventResponse(BaseModel):
    """A rule lifecycle event."""

    id: str
    sequence_number: int | None
    rule_id: str
    version: int
    event_type: str
    event_data: dict[str, Any]
    timestamp: str
    actor: str | None
    reason: str | None


class RuleEventListResponse(BaseModel):
    """Response listing rule events."""

    rule_id: str
    events: list[RuleEventResponse]
    total: int

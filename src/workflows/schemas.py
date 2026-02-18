"""
Pydantic schemas for Temporal workflow inputs and outputs.

Defines data models for:
- ComplianceCheckWorkflow (fan-out/fan-in)
- RuleVerificationWorkflow (sequential saga)
- CounterfactualAnalysisWorkflow (baseline + parallel)
- DriftDetectionWorkflow (cron scheduled)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum, StrEnum
from typing import Any

from pydantic import Field

from src.models import CustomBaseModel

# =============================================================================
# Shared Enums
# =============================================================================


class WorkflowStatus(StrEnum):
    """Workflow execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class VerificationTier(int, Enum):
    """Verification tier levels (0-4)."""

    SCHEMA = 0
    LEXICAL = 1
    SEMANTIC = 2
    NLI = 3
    CROSS_RULE = 4


class JurisdictionStatus(StrEnum):
    """Jurisdiction evaluation status."""

    COMPLIANT = "compliant"
    BLOCKED = "blocked"
    REQUIRES_ACTION = "requires_action"
    NO_APPLICABLE_RULES = "no_applicable_rules"


class ScenarioType(StrEnum):
    """Counterfactual scenario types."""

    JURISDICTION_CHANGE = "jurisdiction_change"
    ENTITY_CHANGE = "entity_change"
    ACTIVITY_RESTRUCTURE = "activity_restructure"
    THRESHOLD = "threshold"
    TEMPORAL = "temporal"
    PROTOCOL_CHANGE = "protocol_change"
    REGULATORY_CHANGE = "regulatory_change"


# =============================================================================
# ComplianceCheckWorkflow Schemas
# =============================================================================


class ComplianceCheckInput(CustomBaseModel):
    """Input for ComplianceCheckWorkflow."""

    issuer_jurisdiction: str = Field(..., description="Issuer's home jurisdiction code")
    target_jurisdictions: list[str] = Field(..., description="Target market jurisdiction codes")
    facts: dict[str, Any] = Field(default_factory=dict, description="Scenario facts for evaluation")
    instrument_type: str | None = Field(None, description="Optional instrument type for regime selection")
    include_equivalences: bool = Field(True, description="Whether to query equivalence determinations")
    detect_conflicts: bool = Field(True, description="Whether to detect inter-jurisdiction conflicts")


class JurisdictionResult(CustomBaseModel):
    """Result for a single jurisdiction evaluation."""

    jurisdiction: str
    regime_id: str
    role: str  # issuer_home or target
    applicable_rules: int
    rules_evaluated: int
    decisions: list[dict[str, Any]]
    obligations: list[dict[str, Any]]
    status: JurisdictionStatus


class EquivalenceResult(CustomBaseModel):
    """Equivalence determination between jurisdictions."""

    id: str
    from_jurisdiction: str
    to_jurisdiction: str
    scope: str | None
    status: str
    effective_date: datetime | None
    expiry_date: datetime | None
    source_reference: str | None
    notes: str | None


class ConflictResult(CustomBaseModel):
    """Detected conflict between jurisdiction decisions."""

    conflict_id: str
    jurisdictions: list[str]
    rule_ids: list[str]
    conflict_type: str
    description: str
    severity: str


class CompliancePathway(CustomBaseModel):
    """Synthesized compliance pathway."""

    feasible: bool
    primary_jurisdiction: str | None
    required_actions: list[str]
    blocking_issues: list[str]
    recommended_sequence: list[str]


class ComplianceCheckOutput(CustomBaseModel):
    """Output from ComplianceCheckWorkflow."""

    workflow_id: str
    status: WorkflowStatus
    started_at: datetime
    completed_at: datetime | None
    issuer_jurisdiction: str
    target_jurisdictions: list[str]
    jurisdiction_results: list[JurisdictionResult]
    equivalences: list[EquivalenceResult]
    conflicts: list[ConflictResult]
    pathway: CompliancePathway | None
    aggregated_obligations: list[dict[str, Any]]
    overall_status: JurisdictionStatus
    error: str | None = None


class ComplianceCheckProgress(CustomBaseModel):
    """Progress update for ComplianceCheckWorkflow."""

    workflow_id: str
    status: WorkflowStatus
    total_jurisdictions: int
    completed_jurisdictions: int
    current_phase: str  # resolving, evaluating, detecting_conflicts, synthesizing
    phase_progress: float  # 0.0 to 1.0


# =============================================================================
# RuleVerificationWorkflow Schemas
# =============================================================================


class RuleVerificationInput(CustomBaseModel):
    """Input for RuleVerificationWorkflow."""

    rule_id: str = Field(..., description="Rule ID to verify")
    source_text: str | None = Field(
        None,
        description="Source regulatory text for semantic checks (tiers 1-3)",
    )
    max_tier: VerificationTier = Field(
        VerificationTier.CROSS_RULE,
        description="Maximum tier to run (will stop early on failure)",
    )
    skip_tiers: list[VerificationTier] = Field(
        default_factory=list,
        description="Tiers to skip",
    )
    fail_fast: bool = Field(True, description="Stop on first tier failure")


class TierResult(CustomBaseModel):
    """Result for a single verification tier."""

    tier: VerificationTier
    tier_name: str
    passed: bool
    score: float  # 0.0 to 1.0
    checks_run: int
    checks_passed: int
    evidence: list[dict[str, Any]]
    duration_ms: float


class RuleVerificationOutput(CustomBaseModel):
    """Output from RuleVerificationWorkflow."""

    workflow_id: str
    status: WorkflowStatus
    started_at: datetime
    completed_at: datetime | None
    rule_id: str
    tier_results: list[TierResult]
    highest_tier_passed: VerificationTier | None
    overall_score: float
    overall_passed: bool
    stopped_early: bool
    stop_reason: str | None
    error: str | None = None


class RuleVerificationProgress(CustomBaseModel):
    """Progress update for RuleVerificationWorkflow."""

    workflow_id: str
    status: WorkflowStatus
    rule_id: str
    current_tier: VerificationTier | None
    tiers_completed: list[VerificationTier]
    tiers_remaining: list[VerificationTier]


# =============================================================================
# CounterfactualAnalysisWorkflow Schemas
# =============================================================================


class CounterfactualScenario(CustomBaseModel):
    """A single counterfactual scenario to analyze."""

    scenario_id: str
    scenario_type: ScenarioType
    description: str
    modified_facts: dict[str, Any]


class CounterfactualInput(CustomBaseModel):
    """Input for CounterfactualAnalysisWorkflow."""

    rule_id: str = Field(..., description="Rule to analyze")
    baseline_facts: dict[str, Any] = Field(..., description="Baseline scenario facts")
    scenarios: list[CounterfactualScenario] = Field(..., description="Counterfactual scenarios")
    include_delta_analysis: bool = Field(True, description="Include delta analysis between scenarios")


class ScenarioResult(CustomBaseModel):
    """Result for a single counterfactual scenario."""

    scenario_id: str
    scenario_type: ScenarioType
    description: str
    decision: str
    applicable: bool
    obligations: list[dict[str, Any]]
    trace: list[dict[str, Any]]
    differs_from_baseline: bool
    key_differences: list[str]


class DeltaAnalysis(CustomBaseModel):
    """Delta analysis between baseline and counterfactual."""

    scenario_id: str
    decision_changed: bool
    original_decision: str
    new_decision: str
    obligations_added: list[str]
    obligations_removed: list[str]
    critical_factors: list[str]


class CounterfactualOutput(CustomBaseModel):
    """Output from CounterfactualAnalysisWorkflow."""

    workflow_id: str
    status: WorkflowStatus
    started_at: datetime
    completed_at: datetime | None
    rule_id: str
    baseline_result: ScenarioResult
    scenario_results: list[ScenarioResult]
    delta_analyses: list[DeltaAnalysis]
    summary: str
    error: str | None = None


class CounterfactualProgress(CustomBaseModel):
    """Progress update for CounterfactualAnalysisWorkflow."""

    workflow_id: str
    status: WorkflowStatus
    total_scenarios: int
    completed_scenarios: int
    current_scenario: str | None


# =============================================================================
# DriftDetectionWorkflow Schemas
# =============================================================================


class DriftDetectionInput(CustomBaseModel):
    """Input for DriftDetectionWorkflow."""

    rule_ids: list[str] | None = Field(
        None,
        description="Specific rules to check (None = all rules)",
    )
    check_schema_drift: bool = Field(True, description="Check for schema changes")
    check_source_drift: bool = Field(True, description="Check for source document changes")
    check_reference_drift: bool = Field(True, description="Check for broken references")
    notify_on_drift: bool = Field(True, description="Send notifications on drift detection")


class RuleDriftResult(CustomBaseModel):
    """Drift detection result for a single rule."""

    rule_id: str
    has_drift: bool
    drift_types: list[str]
    details: list[str]
    severity: str  # low, medium, high, critical
    last_verified: datetime | None
    current_check: datetime


class DriftDetectionOutput(CustomBaseModel):
    """Output from DriftDetectionWorkflow."""

    workflow_id: str
    status: WorkflowStatus
    started_at: datetime
    completed_at: datetime | None
    rules_checked: int
    rules_with_drift: int
    drift_results: list[RuleDriftResult]
    notifications_sent: int
    error: str | None = None


class DriftDetectionProgress(CustomBaseModel):
    """Progress update for DriftDetectionWorkflow."""

    workflow_id: str
    status: WorkflowStatus
    total_rules: int
    checked_rules: int
    drift_detected: int


# =============================================================================
# Schedule Configuration
# =============================================================================


class DriftScheduleConfig(CustomBaseModel):
    """Configuration for scheduled drift detection."""

    schedule_id: str = Field(..., description="Unique schedule identifier")
    cron_expression: str = Field(
        "0 0 * * *",
        description="Cron expression (default: daily at midnight)",
    )
    enabled: bool = Field(True, description="Whether schedule is active")
    input: DriftDetectionInput = Field(
        default_factory=DriftDetectionInput,
        description="Workflow input configuration",
    )


# =============================================================================
# Workflow Info (for status queries)
# =============================================================================


class WorkflowInfo(CustomBaseModel):
    """General workflow information for status queries."""

    workflow_id: str
    workflow_type: str
    status: WorkflowStatus
    started_at: datetime
    completed_at: datetime | None
    run_id: str | None = None
    task_queue: str = "compliance-workflows"

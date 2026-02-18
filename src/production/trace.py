"""Execution tracing for runtime rule evaluation.

Provides detailed traces of how decisions are made, enabling:
- Audit trails for regulatory compliance
- Debugging and explanation generation
- Backward compatibility with existing TraceStep format

From Workbench storage/retrieval/runtime/trace.py.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import Field

from src.models import CustomBaseModel


class TraceStep(CustomBaseModel):
    """A single step in the execution trace."""

    node_id: str
    """Identifier for this step (e.g., 'check_0', 'applicability')."""

    description: str
    """Human-readable description of what was evaluated."""

    field: str | None = None
    operator: str | None = None
    expected_value: Any = None
    actual_value: Any = None
    result: bool | None = None
    source_ref: str | None = None


class ExecutionTrace(CustomBaseModel):
    """Complete execution trace for a rule evaluation."""

    rule_id: str

    started_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str | None = None

    # Applicability evaluation
    applicable: bool = False
    applicability_steps: list[TraceStep] = Field(default_factory=list)

    # Decision evaluation
    decision: str | None = None
    decision_steps: list[TraceStep] = Field(default_factory=list)

    # Metadata
    facts_used: dict[str, Any] = Field(default_factory=dict)
    entry_matched: int | None = None
    obligations: list[dict[str, Any]] = Field(default_factory=list)

    def add_applicability_step(
        self,
        node_id: str,
        description: str,
        field: str | None = None,
        operator: str | None = None,
        expected_value: Any = None,
        actual_value: Any = None,
        result: bool | None = None,
    ) -> TraceStep:
        """Add a step to applicability trace."""
        step = TraceStep(
            node_id=node_id,
            description=description,
            field=field,
            operator=operator,
            expected_value=expected_value,
            actual_value=actual_value,
            result=result,
        )
        self.applicability_steps.append(step)
        return step

    def add_decision_step(
        self,
        node_id: str,
        description: str,
        field: str | None = None,
        operator: str | None = None,
        expected_value: Any = None,
        actual_value: Any = None,
        result: bool | None = None,
        source_ref: str | None = None,
    ) -> TraceStep:
        """Add a step to decision trace."""
        step = TraceStep(
            node_id=node_id,
            description=description,
            field=field,
            operator=operator,
            expected_value=expected_value,
            actual_value=actual_value,
            result=result,
            source_ref=source_ref,
        )
        self.decision_steps.append(step)
        return step

    def complete(self, decision: str | None = None) -> None:
        """Mark the trace as complete."""
        self.decision = decision
        self.completed_at = datetime.now(UTC).isoformat()

    def to_legacy_trace(self) -> list[dict[str, Any]]:
        """Convert to legacy trace format for backward compatibility."""
        legacy = []

        for step in self.applicability_steps:
            legacy.append(
                {
                    "node_id": step.node_id,
                    "description": step.description,
                    "field": step.field,
                    "operator": step.operator,
                    "expected_value": step.expected_value,
                    "actual_value": step.actual_value,
                    "result": step.result,
                }
            )

        for step in self.decision_steps:
            legacy.append(
                {
                    "node_id": step.node_id,
                    "description": step.description,
                    "field": step.field,
                    "operator": step.operator,
                    "expected_value": step.expected_value,
                    "actual_value": step.actual_value,
                    "result": step.result,
                }
            )

        return legacy


class DecisionResult(CustomBaseModel):
    """Result of a rule evaluation."""

    rule_id: str
    applicable: bool
    decision: str | None = None
    obligations: list[dict[str, Any]] = Field(default_factory=list)
    trace: ExecutionTrace | None = None

    @classmethod
    def not_applicable(cls, rule_id: str, trace: ExecutionTrace | None = None) -> DecisionResult:
        """Create a result for when a rule is not applicable."""
        return cls(
            rule_id=rule_id,
            applicable=False,
            trace=trace,
        )

    @classmethod
    def with_decision(
        cls,
        rule_id: str,
        decision: str,
        obligations: list[dict[str, Any]] | None = None,
        trace: ExecutionTrace | None = None,
    ) -> DecisionResult:
        """Create a result with a decision."""
        return cls(
            rule_id=rule_id,
            applicable=True,
            decision=decision,
            obligations=obligations or [],
            trace=trace,
        )

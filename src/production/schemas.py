"""Production IR types and request/response schemas.

Intermediate Representation (IR) types for compiled rules, enabling:
- O(1) rule lookup via premise index
- Linear condition evaluation (no tree traversal)
- Jump-table style decision lookup

From Workbench storage/retrieval/compiler/ir.py.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import ConfigDict, Field

from src.models import CustomBaseModel
from src.ontology.jurisdiction import (
    EquivalenceRef,
    Jurisdiction,
    JurisdictionCode,
)

# =============================================================================
# IR Types (from Workbench storage/retrieval/compiler/ir.py)
# =============================================================================


class ObligationSpec(CustomBaseModel):
    """An obligation triggered by a decision."""

    id: str
    description: str | None = None
    deadline: str | None = None


class CompiledCheck(CustomBaseModel):
    """A single flattened condition check.

    Conditions are compiled to a linear sequence for efficient evaluation.
    Each check can specify jump targets for control flow.
    """

    index: int
    """Position in the check sequence."""

    field: str
    """The fact field to check."""

    op: Literal["eq", "ne", "in", "not_in", "gt", "lt", "gte", "lte", "exists"]
    """The comparison operator."""

    value: Any = None
    """The value to compare against."""

    value_set: set[str] | None = None
    """Pre-computed set for O(1) 'in' operator lookups."""

    on_true: int | None = None
    """Jump target index if check passes (None = continue to next)."""

    on_false: int | None = None
    """Jump target index if check fails (None = continue to next)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def model_dump(self, *args: Any, **kwargs: Any) -> dict:
        """Override to convert set to list for JSON serialization."""
        data = super().model_dump(*args, **kwargs)
        if data.get("value_set") is not None:
            data["value_set"] = list(data["value_set"])
        return data

    @classmethod
    def model_validate(cls, obj: Any, **kwargs: Any) -> CompiledCheck:
        """Override to convert list back to set for value_set."""
        if isinstance(obj, dict) and obj.get("value_set") is not None:
            obj = dict(obj)
            obj["value_set"] = set(obj["value_set"])
        return super().model_validate(obj, **kwargs)


class DecisionEntry(CustomBaseModel):
    """A single entry in the decision table.

    The decision table replaces tree traversal with direct lookup.
    Each entry specifies conditions that must be satisfied for this outcome.
    """

    entry_id: int
    """Unique identifier within the decision table."""

    condition_mask: list[int]
    """
    Condition evaluation requirements:
    - Positive index (+i): check at index i must be True
    - Negative index (-i): check at index i must be False
    - Zero (0): don't care / wildcard
    """

    result: str
    """The decision result (e.g., 'authorized', 'not_authorized', 'exempt')."""

    obligations: list[ObligationSpec] = Field(default_factory=list)
    """Obligations triggered by this decision."""

    source_ref: str | None = None
    """Reference to source legal text (e.g., 'Article 36(2)')."""

    notes: str | None = None
    """Additional notes about this decision path."""


class RuleIR(CustomBaseModel):
    """Complete Intermediate Representation of a compiled rule.

    This is the serialized format stored in the database and loaded at runtime.
    Extended with jurisdiction support for v4 architecture.
    """

    rule_id: str
    """Unique rule identifier."""

    version: int = 1
    """Rule content version."""

    ir_version: int = 2
    """IR format version for compatibility. v2 adds jurisdiction support."""

    # Jurisdiction Scoping (v4 multi-jurisdiction support)
    jurisdiction: Jurisdiction | None = None
    jurisdiction_code: JurisdictionCode = JurisdictionCode.EU
    regime_id: str = "mica_2023"
    cross_border_relevant: bool = False
    equivalence_refs: list[EquivalenceRef] = Field(default_factory=list)
    conflicts_with: list[str] = Field(default_factory=list)

    # O(1) Lookup Keys
    premise_keys: list[str] = Field(default_factory=list)
    """Premise keys for inverted index lookup. Format: 'field:value'."""

    # Applicability Checks
    applicability_checks: list[CompiledCheck] = Field(default_factory=list)
    applicability_mode: Literal["all", "any"] = "all"

    # Decision Table
    decision_checks: list[CompiledCheck] = Field(default_factory=list)
    decision_table: list[DecisionEntry] = Field(default_factory=list)

    # Dependency Graph (for multi-rule chaining)
    produces: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    priority: int = 0

    # Pre-extracted Obligations
    all_obligations: list[dict] = Field(default_factory=list)

    # Metadata
    compiled_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    source_hash: str | None = None
    source_document_id: str | None = None
    source_article: str | None = None

    def to_json(self) -> str:
        """Serialize to JSON string for database storage."""
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> RuleIR:
        """Deserialize from JSON string."""
        return cls.model_validate_json(json_str)


# Type aliases
ConditionMask = list[int]
PremiseKey = str


# =============================================================================
# API Request/Response Schemas
# =============================================================================


class CompileRequest(CustomBaseModel):
    """Request to compile one or more rules."""

    rule_ids: list[str] = Field(
        default_factory=list,
        description="Specific rule IDs to compile (empty = compile all)",
    )
    force: bool = Field(
        False,
        description="Force recompilation even if IR is up-to-date",
    )


class CompileResponse(CustomBaseModel):
    """Result of rule compilation."""

    compiled_count: int
    skipped_count: int = 0
    errors: list[dict] = Field(default_factory=list)
    compiled_rules: list[str] = Field(default_factory=list)


class EvaluateRequest(CustomBaseModel):
    """Request to evaluate facts against compiled rules."""

    facts: dict[str, Any]
    rule_ids: list[str] | None = None
    jurisdiction: str | None = None


class EvaluateResponse(CustomBaseModel):
    """Result of compiled rule evaluation."""

    results: list[dict]
    trace: list[dict] = Field(default_factory=list)
    evaluation_time_ms: float = 0.0

"""Rules service layer - rule loading, validation, and decision engine."""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from pydantic import BaseModel, Field

from src.ontology.jurisdiction import JurisdictionCode

if TYPE_CHECKING:
    from src.ontology.scenario import Scenario

# =============================================================================
# Source Reference
# =============================================================================


class SourceRef(BaseModel):
    """Source reference linking a rule to its legal text."""

    document_id: str = Field(..., description="Document identifier (e.g., 'mica_2023')")
    article: str | None = Field(None, description="Article number (e.g., '36(1)')")
    section: str | None = Field(None, description="Section identifier")
    paragraphs: list[str] = Field(default_factory=list, description="Paragraph references")
    pages: list[int] = Field(default_factory=list, description="Page numbers")
    url: str | None = Field(None, description="URL to source document")


# =============================================================================
# Condition Expressions
# =============================================================================


class ComparisonOp(StrEnum):
    """Comparison operators for conditions."""

    EQ = "=="
    NE = "!="
    LT = "<"
    LE = "<="
    GT = ">"
    GE = ">="
    IN = "in"
    NOT_IN = "not_in"
    EXISTS = "exists"


class ConditionSpec(BaseModel):
    """A single condition specification."""

    field: str = Field(..., description="Field name to evaluate")
    operator: str = Field("==", description="Comparison operator")
    value: Any = Field(None, description="Expected value")
    description: str | None = Field(None, description="Human-readable description")


class ConditionGroupSpec(BaseModel):
    """Grouped conditions with logical operators."""

    all: list[ConditionSpec | ConditionGroupSpec] | None = Field(None, description="All conditions must be true (AND)")
    any: list[ConditionSpec | ConditionGroupSpec] | None = Field(None, description="Any condition must be true (OR)")


# =============================================================================
# Obligations
# =============================================================================


class ObligationSpec(BaseModel):
    """An obligation triggered by a decision."""

    id: str = Field(..., description="Obligation identifier")
    description: str | None = Field(None, description="Human-readable description")
    deadline: str | None = Field(None, description="Deadline specification")
    source_ref: str | None = Field(None, description="Source article reference")


class ObligationResult(BaseModel):
    """An obligation result from a decision."""

    id: str
    description: str | None = None
    source: str | None = None
    deadline: str | None = None


# =============================================================================
# Decision Tree
# =============================================================================


class DecisionLeaf(BaseModel):
    """A leaf node (terminal result) in the decision tree."""

    result: str = Field(..., description="Decision outcome")
    obligations: list[ObligationSpec] = Field(default_factory=list)
    notes: str | None = Field(None, description="Explanation notes")


class DecisionNode(BaseModel):
    """A branch node in the decision tree."""

    node_id: str = Field(..., description="Node identifier for tracing")
    condition: ConditionSpec | None = Field(None, description="Branch condition")
    true_branch: DecisionNode | DecisionLeaf | None = Field(None, description="Path if condition is true")
    false_branch: DecisionNode | DecisionLeaf | None = Field(None, description="Path if condition is false")


# =============================================================================
# Consistency / QA Metadata
# =============================================================================


class ConsistencyStatus(StrEnum):
    """Status of consistency verification."""

    VERIFIED = "verified"
    NEEDS_REVIEW = "needs_review"
    INCONSISTENT = "inconsistent"
    UNVERIFIED = "unverified"


class ConsistencyLabel(StrEnum):
    """Labels for consistency evidence."""

    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    ENTAILS = "entails"
    NEUTRAL = "neutral"
    CONTRADICTS = "contradicts"


class ConsistencyEvidence(BaseModel):
    """A single piece of consistency verification evidence."""

    tier: int = Field(..., ge=0, le=4, description="Verification tier (0-4)")
    category: str = Field(..., description="Check category (e.g., 'deontic_alignment')")
    label: str = Field(..., description="Result label (pass/fail/warning/etc.)")
    score: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    details: str = Field(..., description="Human-readable explanation")
    source_span: str | None = Field(None, description="Relevant text from source")
    rule_element: str | None = Field(None, description="Path to rule element")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        description="ISO 8601 timestamp",
    )


class ConsistencySummary(BaseModel):
    """Summary of consistency verification results."""

    status: ConsistencyStatus = Field(default=ConsistencyStatus.UNVERIFIED, description="Overall verification status")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Weighted confidence score")
    last_verified: str | None = Field(None, description="ISO 8601 timestamp")
    verified_by: str | None = Field(None, description="'system' or 'human:username'")
    notes: str | None = Field(None, description="Optional reviewer notes")


class ConsistencyBlock(BaseModel):
    """Complete consistency metadata for a rule."""

    summary: ConsistencySummary = Field(default_factory=ConsistencySummary)
    evidence: list[ConsistencyEvidence] = Field(default_factory=list)


# =============================================================================
# Rule Model
# =============================================================================


class Rule(BaseModel):
    """A complete rule specification."""

    rule_id: str = Field(..., description="Unique rule identifier")
    version: str = Field(default="1.0", description="Rule version")
    description: str | None = Field(None, description="Human-readable description")
    effective_from: date | None = Field(None, description="When rule becomes active")
    effective_to: date | None = Field(None, description="When rule expires")
    tags: list[str] = Field(default_factory=list, description="Classification tags")

    # Jurisdiction scoping
    jurisdiction: JurisdictionCode = Field(
        default=JurisdictionCode.EU, description="Primary jurisdiction for this rule"
    )
    regime_id: str = Field(default="mica_2023", description="Regulatory regime identifier")
    cross_border_relevant: bool = Field(
        default=False, description="Whether this rule applies in cross-border scenarios"
    )

    # Logic
    applies_if: ConditionGroupSpec | None = Field(None, description="Applicability conditions")
    decision_tree: DecisionNode | DecisionLeaf | None = Field(None, description="Decision logic")

    # Source
    source: SourceRef | None = Field(None, description="Source citation")
    interpretation_notes: str | None = Field(None, description="Explanation of modeling choices")

    # QA / Consistency
    consistency: ConsistencyBlock | None = Field(None, description="Verification metadata")


class RulePack(BaseModel):
    """A collection of related rules."""

    pack_id: str = Field(..., description="Pack identifier")
    name: str = Field(..., description="Pack name")
    description: str = Field(..., description="Pack description")
    version: str = Field(default="1.0", description="Pack version")
    rules: list[Rule] = Field(default_factory=list, description="Rules in this pack")


# Enable forward references
ConditionGroupSpec.model_rebuild()
DecisionNode.model_rebuild()

# Backwards compatibility alias
DecisionBranch = DecisionNode


# =============================================================================
# Decision Engine Types
# =============================================================================


class TraceStep(BaseModel):
    """A single step in the decision trace."""

    node: str
    condition: str
    result: bool
    value_checked: Any = None
    annotation_id: str | None = None
    regulatory_version: str | None = None
    interpretation_note: str | None = None


class RuleMetadata(BaseModel):
    """Metadata about the rule that produced a decision."""

    rule_id: str
    version: str = "1.0"
    source: SourceRef | None = None
    consistency: ConsistencyBlock | None = None
    tags: list[str] = Field(default_factory=list)


class DecisionResult(BaseModel):
    """Complete result of a decision evaluation."""

    rule_id: str
    applicable: bool = True
    decision: str | None = None
    trace: list[TraceStep] = Field(default_factory=list)
    obligations: list[ObligationResult] = Field(default_factory=list)
    source: str | None = None
    notes: str | None = None
    rule_metadata: RuleMetadata | None = None


# =============================================================================
# Rule Loader
# =============================================================================


class RuleLoader:
    """Loads and validates YAML rules from files or directories."""

    def __init__(self, rules_dir: str | Path | None = None):
        self.rules_dir = Path(rules_dir) if rules_dir else None
        self._rules: dict[str, Rule] = {}

    def load_file(self, path: str | Path) -> list[Rule]:
        """Load rules from a single YAML file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Rule file not found: {path}")

        with open(path, encoding="utf-8") as f:
            content = yaml.safe_load(f)

        rules = []
        if isinstance(content, list):
            for item in content:
                rule = self._parse_rule(item)
                rules.append(rule)
                self._rules[rule.rule_id] = rule
        else:
            rule = self._parse_rule(content)
            rules.append(rule)
            self._rules[rule.rule_id] = rule

        return rules

    def load_directory(self, path: str | Path | None = None) -> list[Rule]:
        """Load all YAML rules from a directory."""
        path = Path(path) if path else self.rules_dir
        if not path:
            raise ValueError("No rules directory specified")
        if not path.exists():
            raise FileNotFoundError(f"Rules directory not found: {path}")

        rules = []
        for yaml_file in path.glob("*.yaml"):
            if yaml_file.name == "schema.yaml":
                continue
            try:
                rules.extend(self.load_file(yaml_file))
            except Exception as e:
                print(f"Warning: Failed to load {yaml_file}: {e}")

        return rules

    def get_rule(self, rule_id: str) -> Rule | None:
        """Get a loaded rule by ID."""
        return self._rules.get(rule_id)

    def get_all_rules(self) -> list[Rule]:
        """Get all loaded rules."""
        return list(self._rules.values())

    def get_applicable_rules(self, tags: list[str] | None = None) -> list[Rule]:
        """Get rules filtered by tags and effective date."""
        today = date.today()
        rules = []

        for rule in self._rules.values():
            if rule.effective_from and rule.effective_from > today:
                continue
            if rule.effective_to and rule.effective_to < today:
                continue
            if tags and not any(tag in rule.tags for tag in tags):
                continue
            rules.append(rule)

        return rules

    def _parse_rule(self, data: dict) -> Rule:
        """Parse a rule from dictionary data."""
        if "applies_if" in data and data["applies_if"]:
            data["applies_if"] = self._parse_condition_group(data["applies_if"])

        if "decision_tree" in data and data["decision_tree"]:
            data["decision_tree"] = self._parse_decision_node(data["decision_tree"])

        if "consistency" in data and data["consistency"]:
            data["consistency"] = self._parse_consistency(data["consistency"])

        return Rule(**data)

    def _parse_consistency(self, data: dict) -> ConsistencyBlock:
        """Parse a consistency block."""
        summary_data = data.get("summary", {})
        summary = ConsistencySummary(
            status=ConsistencyStatus(summary_data.get("status", "unverified")),
            confidence=summary_data.get("confidence", 0.0),
            last_verified=summary_data.get("last_verified"),
            verified_by=summary_data.get("verified_by"),
            notes=summary_data.get("notes"),
        )

        evidence = []
        for ev_data in data.get("evidence", []):
            evidence.append(
                ConsistencyEvidence(
                    tier=ev_data.get("tier", 0),
                    category=ev_data.get("category", "unknown"),
                    label=ev_data.get("label", "warning"),
                    score=ev_data.get("score", 0.0),
                    details=ev_data.get("details", ""),
                    source_span=ev_data.get("source_span"),
                    rule_element=ev_data.get("rule_element"),
                    timestamp=ev_data.get("timestamp", ""),
                )
            )

        return ConsistencyBlock(summary=summary, evidence=evidence)

    def _parse_condition_group(self, data: dict) -> ConditionGroupSpec:
        """Parse a condition group."""
        result = {}
        if "all" in data:
            result["all"] = [self._parse_condition_or_group(c) for c in data["all"]]
        if "any" in data:
            result["any"] = [self._parse_condition_or_group(c) for c in data["any"]]
        return ConditionGroupSpec(**result)

    def _parse_condition_or_group(self, data: dict) -> ConditionSpec | ConditionGroupSpec:
        """Parse either a condition or a condition group."""
        if "field" in data:
            return ConditionSpec(**data)
        return self._parse_condition_group(data)

    def _parse_decision_node(self, data: dict) -> DecisionNode | DecisionLeaf:
        """Parse a decision tree node or leaf."""
        if "result" in data:
            obligations = []
            if "obligations" in data:
                obligations = [ObligationSpec(**o) for o in data["obligations"]]
            return DecisionLeaf(
                result=data["result"],
                obligations=obligations,
                notes=data.get("notes"),
            )

        condition = None
        if "condition" in data:
            cond_data = data["condition"]
            if isinstance(cond_data, dict):
                condition = ConditionSpec(**cond_data)
            elif isinstance(cond_data, str):
                condition = self._parse_string_condition(cond_data)

        true_branch = None
        false_branch = None
        if "true_branch" in data and data["true_branch"]:
            true_branch = self._parse_decision_node(data["true_branch"])
        if "false_branch" in data and data["false_branch"]:
            false_branch = self._parse_decision_node(data["false_branch"])

        return DecisionNode(
            node_id=data.get("node_id", "unnamed"),
            condition=condition,
            true_branch=true_branch,
            false_branch=false_branch,
        )

    def _parse_string_condition(self, cond_str: str) -> ConditionSpec:
        """Parse a string condition like 'authorized == true'."""
        operators = ["==", "!=", ">=", "<=", ">", "<", " in "]
        for op in operators:
            if op in cond_str:
                parts = cond_str.split(op)
                if len(parts) == 2:
                    field = parts[0].strip()
                    value_str = parts[1].strip()
                    value = self._parse_value(value_str)
                    return ConditionSpec(field=field, operator=op.strip(), value=value)

        return ConditionSpec(field=cond_str.strip(), operator="exists", value=True)

    def _parse_value(self, value_str: str) -> Any:
        """Parse a string value into appropriate type."""
        if value_str.lower() == "true":
            return True
        if value_str.lower() == "false":
            return False

        if value_str.startswith("[") and value_str.endswith("]"):
            inner = value_str[1:-1]
            items = [item.strip().strip("'\"") for item in inner.split(",")]
            return items

        try:
            if "." in value_str:
                return float(value_str)
            return int(value_str)
        except ValueError:
            pass

        return value_str.strip("'\"")

    def save_rule(self, rule: Rule, path: str | Path | None = None) -> Path:
        """Save a rule to a YAML file."""
        if path is None:
            if self.rules_dir is None:
                raise ValueError("No rules directory specified and no path provided")
            path = self.rules_dir / f"{rule.rule_id}.yaml"
        else:
            path = Path(path)

        data = self._rule_to_dict(rule)

        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        self._rules[rule.rule_id] = rule
        return path

    def _rule_to_dict(self, rule: Rule) -> dict:
        """Convert a Rule to a dictionary suitable for YAML serialization."""
        return rule.model_dump(mode="json", exclude_none=True, exclude_unset=True)

    def update_rule(self, rule_id: str, updates: dict) -> Rule:
        """Update a rule with new values and save."""
        rule = self.get_rule(rule_id)
        if not rule:
            raise ValueError(f"Rule not found: {rule_id}")

        rule_data = rule.model_dump()
        rule_data.update(updates)

        updated_rule = Rule(**rule_data)
        self._rules[rule_id] = updated_rule

        return updated_rule

    def get_rules_by_document(self, document_id: str) -> list[Rule]:
        """Get all rules that reference a specific document."""
        return [rule for rule in self._rules.values() if rule.source and rule.source.document_id == document_id]


# =============================================================================
# Decision Engine
# =============================================================================


class DecisionEngine:
    """Evaluates rules against scenarios with full tracing."""

    def __init__(self, loader: RuleLoader | None = None):
        self.loader = loader or RuleLoader()

    def evaluate(self, scenario: Scenario, rule_id: str) -> DecisionResult:
        """Evaluate a specific rule against a scenario."""
        rule = self.loader.get_rule(rule_id)
        if not rule:
            return DecisionResult(
                rule_id=rule_id,
                applicable=False,
                decision="rule_not_found",
            )

        return self._evaluate_rule(rule, scenario)

    def evaluate_all(self, scenario: Scenario) -> list[DecisionResult]:
        """Evaluate all applicable rules against a scenario."""
        results = []
        for rule in self.loader.get_all_rules():
            result = self._evaluate_rule(rule, scenario)
            if result.applicable:
                results.append(result)
        return results

    def _evaluate_rule(self, rule: Rule, scenario: Scenario) -> DecisionResult:
        """Evaluate a single rule against a scenario."""
        context = scenario.to_flat_dict()
        trace: list[TraceStep] = []

        # Build source string
        source_str = None
        if rule.source:
            parts = [rule.source.document_id]
            if rule.source.article:
                parts.append(f"Art. {rule.source.article}")
            if rule.source.pages:
                parts.append(f"p. {', '.join(map(str, rule.source.pages))}")
            source_str = " ".join(parts)

        # Build rule metadata
        rule_metadata = RuleMetadata(
            rule_id=rule.rule_id,
            version=rule.version,
            source=rule.source,
            consistency=rule.consistency,
            tags=rule.tags,
        )

        # Check applies_if conditions
        if rule.applies_if:
            applies, applies_trace = self._evaluate_condition_group(rule.applies_if, context, "applicability")
            trace.extend(applies_trace)

            if not applies:
                return DecisionResult(
                    rule_id=rule.rule_id,
                    applicable=False,
                    decision="not_applicable",
                    trace=trace,
                    source=source_str,
                    rule_metadata=rule_metadata,
                )

        # Evaluate decision tree
        if rule.decision_tree:
            decision, obligations, tree_trace = self._evaluate_decision_tree(rule.decision_tree, context, rule.source)
            trace.extend(tree_trace)

            return DecisionResult(
                rule_id=rule.rule_id,
                applicable=True,
                decision=decision,
                trace=trace,
                obligations=obligations,
                source=source_str,
                notes=rule.interpretation_notes,
                rule_metadata=rule_metadata,
            )

        # Rule has no decision tree (informational only)
        return DecisionResult(
            rule_id=rule.rule_id,
            applicable=True,
            decision="applicable",
            trace=trace,
            source=source_str,
            notes=rule.interpretation_notes,
            rule_metadata=rule_metadata,
        )

    def _evaluate_condition_group(
        self, group: ConditionGroupSpec, context: dict, prefix: str
    ) -> tuple[bool, list[TraceStep]]:
        """Evaluate a condition group (all/any)."""
        trace = []

        if group.all:
            for i, cond in enumerate(group.all):
                if isinstance(cond, ConditionGroupSpec):
                    result, sub_trace = self._evaluate_condition_group(cond, context, f"{prefix}.all[{i}]")
                    trace.extend(sub_trace)
                else:
                    result, step = self._evaluate_condition(cond, context, f"{prefix}.all[{i}]")
                    trace.append(step)

                if not result:
                    return False, trace

            return True, trace

        if group.any:
            for i, cond in enumerate(group.any):
                if isinstance(cond, ConditionGroupSpec):
                    result, sub_trace = self._evaluate_condition_group(cond, context, f"{prefix}.any[{i}]")
                    trace.extend(sub_trace)
                else:
                    result, step = self._evaluate_condition(cond, context, f"{prefix}.any[{i}]")
                    trace.append(step)

                if result:
                    return True, trace

            return False, trace

        return True, trace

    def _evaluate_condition(self, cond: ConditionSpec, context: dict, node_id: str) -> tuple[bool, TraceStep]:
        """Evaluate a single condition."""
        field = cond.field
        op = cond.operator
        expected = cond.value
        actual = context.get(field)

        condition_str = f"{field} {op} {expected}"
        result = False

        if op == "==":
            result = actual == expected
        elif op == "!=":
            result = actual != expected
        elif op == "in":
            result = actual in expected if isinstance(expected, list) else False
        elif op == "not_in":
            result = actual not in expected if isinstance(expected, list) else True
        elif op == ">":
            result = actual is not None and actual > expected
        elif op == "<":
            result = actual is not None and actual < expected
        elif op == ">=":
            result = actual is not None and actual >= expected
        elif op == "<=":
            result = actual is not None and actual <= expected
        elif op == "exists":
            result = actual is not None

        step = TraceStep(
            node=node_id,
            condition=condition_str,
            result=result,
            value_checked=actual,
        )
        return result, step

    def _evaluate_decision_tree(
        self, node: DecisionNode | DecisionLeaf, context: dict, source: SourceRef | None
    ) -> tuple[str, list[ObligationResult], list[TraceStep]]:
        """Evaluate a decision tree."""
        trace = []

        # Leaf node
        if isinstance(node, DecisionLeaf):
            obligations = []
            for obl in node.obligations:
                obl_source = None
                if source:
                    parts = [source.document_id]
                    if source.article:
                        parts.append(f"Art. {source.article}")
                    if source.pages:
                        parts.append(f"p. {', '.join(map(str, source.pages))}")
                    obl_source = " ".join(parts)

                obligations.append(
                    ObligationResult(
                        id=obl.id,
                        description=obl.description,
                        source=obl_source,
                        deadline=obl.deadline,
                    )
                )
            return node.result, obligations, trace

        # Branch node
        if node.condition:
            result, step = self._evaluate_condition(node.condition, context, node.node_id)
            trace.append(step)

            next_node = node.true_branch if result else node.false_branch
            if next_node:
                decision, obligations, sub_trace = self._evaluate_decision_tree(next_node, context, source)
                trace.extend(sub_trace)
                return decision, obligations, trace

        return "no_decision", [], trace

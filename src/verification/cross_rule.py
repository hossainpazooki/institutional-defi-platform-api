"""Tier 4: Cross-Rule Consistency Checking.

Provides multi-rule coherence verification including:
- Contradiction detection between rule outcomes
- Hierarchy consistency (lex specialis)
- Temporal consistency (no conflicting rules active in same period)

All checks are deterministic (no ML required).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.rules.service import (
        ConditionGroupSpec,
        ConditionSpec,
        DecisionLeaf,
        DecisionNode,
        Rule,
    )

from src.rules.service import ConsistencyEvidence

# =============================================================================
# Result Dataclasses
# =============================================================================


@dataclass
class ContradictionResult:
    has_contradiction: bool
    contradicting_rule_ids: list[str] = field(default_factory=list)
    contradiction_pairs: list[dict] = field(default_factory=list)
    severity: str = "none"
    details: str = ""


@dataclass
class HierarchyResult:
    is_consistent: bool
    violations: list[dict] = field(default_factory=list)
    specificity_scores: dict[str, int] = field(default_factory=dict)
    details: str = ""


@dataclass
class TemporalResult:
    is_consistent: bool
    overlapping_conflicts: list[dict] = field(default_factory=list)
    timeline_gaps: list[dict] = field(default_factory=list)
    details: str = ""


# =============================================================================
# Cross-Rule Checker
# =============================================================================


class CrossRuleChecker:
    """Multi-rule coherence checking with 3 sub-checks."""

    CONTRADICTING_OUTCOMES: set[tuple[str, str]] = {
        ("permitted", "prohibited"),
        ("required", "forbidden"),
        ("authorized", "denied"),
        ("compliant", "non_compliant"),
        ("exempt", "subject_to"),
        ("allowed", "forbidden"),
        ("mandatory", "optional"),
    }

    MIN_DATE = date(1900, 1, 1)
    MAX_DATE = date(2999, 12, 31)

    def __init__(self, related_rules: list[Rule] | None = None):
        self.related_rules = related_rules or []

    def check_all(self, rule: Rule) -> list[ConsistencyEvidence]:
        return [
            self.check_contradiction(rule),
            self.check_hierarchy(rule),
            self.check_temporal_consistency(rule),
        ]

    def check_contradiction(self, rule: Rule) -> ConsistencyEvidence:
        """Check for contradicting outcomes between rules."""
        timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        if not self.related_rules:
            return ConsistencyEvidence(
                tier=4,
                category="no_contradiction",
                label="pass",
                score=1.0,
                details="No related rules provided for comparison.",
                timestamp=timestamp,
            )

        primary_outcomes = self._extract_outcomes(rule)
        contradictions: list[dict] = []
        contradicting_ids: list[str] = []

        for other in self.related_rules:
            if other.rule_id == rule.rule_id:
                continue

            other_outcomes = self._extract_outcomes(other)
            for p_outcome in primary_outcomes:
                for o_outcome in other_outcomes:
                    if self._are_contradicting(p_outcome, o_outcome):
                        conditions_overlap = self._conditions_overlap(rule, other)
                        contradictions.append(
                            {
                                "rule1_id": rule.rule_id,
                                "rule1_outcome": p_outcome,
                                "rule2_id": other.rule_id,
                                "rule2_outcome": o_outcome,
                                "conditions_overlap": conditions_overlap,
                            }
                        )
                        if other.rule_id not in contradicting_ids:
                            contradicting_ids.append(other.rule_id)

        if not contradictions:
            return ConsistencyEvidence(
                tier=4,
                category="no_contradiction",
                label="pass",
                score=1.0,
                details="No contradicting outcomes found with related rules.",
                rule_element="decision_tree",
                timestamp=timestamp,
            )

        has_overlap = any(c["conditions_overlap"] for c in contradictions)
        if has_overlap:
            return ConsistencyEvidence(
                tier=4,
                category="no_contradiction",
                label="fail",
                score=0.2,
                details=(
                    f"Found {len(contradictions)} contradiction(s) with overlapping conditions. "
                    f"Conflicting rules: {', '.join(contradicting_ids)}."
                ),
                rule_element="decision_tree",
                timestamp=timestamp,
            )

        return ConsistencyEvidence(
            tier=4,
            category="no_contradiction",
            label="warning",
            score=0.7,
            details=(
                f"Found {len(contradictions)} potential contradiction(s) but conditions appear disjoint. "
                f"Rules: {', '.join(contradicting_ids)}."
            ),
            rule_element="decision_tree",
            timestamp=timestamp,
        )

    def check_hierarchy(self, rule: Rule) -> ConsistencyEvidence:
        """Check lex specialis hierarchy consistency."""
        timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        if not self.related_rules:
            return ConsistencyEvidence(
                tier=4,
                category="hierarchy_consistent",
                label="pass",
                score=1.0,
                details="No related rules provided for hierarchy comparison.",
                timestamp=timestamp,
            )

        primary_specificity = self._calculate_specificity(rule)
        primary_outcomes = self._extract_outcomes(rule)
        violations: list[dict] = []

        for other in self.related_rules:
            if other.rule_id == rule.rule_id:
                continue

            other_specificity = self._calculate_specificity(other)
            other_outcomes = self._extract_outcomes(other)

            has_conflict = any(self._are_contradicting(p, o) for p in primary_outcomes for o in other_outcomes)

            if has_conflict and primary_specificity != other_specificity:
                more_specific = rule.rule_id if primary_specificity > other_specificity else other.rule_id
                less_specific = other.rule_id if primary_specificity > other_specificity else rule.rule_id
                violations.append(
                    {
                        "more_specific_rule": more_specific,
                        "less_specific_rule": less_specific,
                        "more_specific_score": max(primary_specificity, other_specificity),
                        "less_specific_score": min(primary_specificity, other_specificity),
                    }
                )

        if not violations:
            return ConsistencyEvidence(
                tier=4,
                category="hierarchy_consistent",
                label="pass",
                score=1.0,
                details=(f"Rule specificity score: {primary_specificity}. No lex specialis violations found."),
                rule_element="applies_if,decision_tree",
                timestamp=timestamp,
            )

        return ConsistencyEvidence(
            tier=4,
            category="hierarchy_consistent",
            label="warning",
            score=0.6,
            details=(
                f"Found {len(violations)} hierarchy violation(s). "
                f"Rule specificity: {primary_specificity}. "
                "Consider ordering rules to ensure more specific rules take precedence."
            ),
            rule_element="applies_if,decision_tree",
            timestamp=timestamp,
        )

    def check_temporal_consistency(self, rule: Rule) -> ConsistencyEvidence:
        """Check for temporal conflicts between rule validity periods."""
        timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        if not self.related_rules:
            return ConsistencyEvidence(
                tier=4,
                category="temporal_consistent",
                label="pass",
                score=1.0,
                details="No related rules provided for temporal comparison.",
                timestamp=timestamp,
            )

        primary_outcomes = self._extract_outcomes(rule)
        overlapping_conflicts: list[dict] = []

        for other in self.related_rules:
            if other.rule_id == rule.rule_id:
                continue

            other_outcomes = self._extract_outcomes(other)
            has_conflict = any(self._are_contradicting(p, o) for p in primary_outcomes for o in other_outcomes)

            if not has_conflict:
                continue

            overlaps, overlap_start, overlap_end = self._periods_overlap(
                rule.effective_from,
                rule.effective_to,
                other.effective_from,
                other.effective_to,
            )

            if overlaps:
                overlapping_conflicts.append(
                    {
                        "rule1_id": rule.rule_id,
                        "rule2_id": other.rule_id,
                        "overlap_start": overlap_start.isoformat() if overlap_start else None,
                        "overlap_end": overlap_end.isoformat() if overlap_end else None,
                    }
                )

        if not overlapping_conflicts:
            return ConsistencyEvidence(
                tier=4,
                category="temporal_consistent",
                label="pass",
                score=1.0,
                details=(
                    f"Rule validity: {rule.effective_from or 'unbounded'} to "
                    f"{rule.effective_to or 'unbounded'}. No temporal conflicts found."
                ),
                rule_element="effective_from,effective_to",
                timestamp=timestamp,
            )

        conflict_ids = [c["rule2_id"] for c in overlapping_conflicts]
        return ConsistencyEvidence(
            tier=4,
            category="temporal_consistent",
            label="warning",
            score=0.5,
            details=(
                f"Found {len(overlapping_conflicts)} temporal conflict(s). "
                f"Conflicting rules active in same period: {', '.join(conflict_ids)}."
            ),
            rule_element="effective_from,effective_to",
            timestamp=timestamp,
        )

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _extract_outcomes(self, rule: Rule) -> list[str]:
        outcomes: list[str] = []
        if rule.decision_tree is None:
            return outcomes

        def traverse(node: DecisionNode | DecisionLeaf) -> None:
            from src.rules.service import DecisionLeaf, DecisionNode

            if isinstance(node, DecisionLeaf):
                if node.result:
                    outcomes.append(node.result.lower().strip())
            elif isinstance(node, DecisionNode):
                if node.true_branch:
                    traverse(node.true_branch)
                if node.false_branch:
                    traverse(node.false_branch)

        traverse(rule.decision_tree)
        return outcomes

    def _are_contradicting(self, outcome1: str, outcome2: str) -> bool:
        return (outcome1, outcome2) in self.CONTRADICTING_OUTCOMES or (
            outcome2,
            outcome1,
        ) in self.CONTRADICTING_OUTCOMES

    def _conditions_overlap(self, rule1: Rule, rule2: Rule) -> bool:
        if rule1.applies_if is None or rule2.applies_if is None:
            return True
        fields1 = self._extract_condition_fields(rule1.applies_if)
        fields2 = self._extract_condition_fields(rule2.applies_if)
        return not (fields1 and fields2 and not fields1.intersection(fields2))

    def _extract_condition_fields(self, condition: ConditionSpec | ConditionGroupSpec) -> set[str]:
        from src.rules.service import ConditionGroupSpec, ConditionSpec

        fields: set[str] = set()
        if isinstance(condition, ConditionSpec):
            if condition.field:
                fields.add(condition.field)
        elif isinstance(condition, ConditionGroupSpec):
            items = []
            if condition.all:
                items.extend(condition.all)
            if condition.any:
                items.extend(condition.any)
            for item in items:
                fields.update(self._extract_condition_fields(item))
        return fields

    def _calculate_specificity(self, rule: Rule) -> int:
        specificity = 0
        if rule.applies_if:
            specificity += self._count_conditions(rule.applies_if)
        if rule.decision_tree:
            specificity += self._count_tree_nodes(rule.decision_tree)
        return specificity

    def _count_conditions(self, condition: ConditionSpec | ConditionGroupSpec) -> int:
        from src.rules.service import ConditionGroupSpec, ConditionSpec

        if isinstance(condition, ConditionSpec):
            return 1
        elif isinstance(condition, ConditionGroupSpec):
            count = 0
            if condition.all:
                for item in condition.all:
                    count += self._count_conditions(item)
            if condition.any:
                for item in condition.any:
                    count += self._count_conditions(item)
            return count
        return 0

    def _count_tree_nodes(self, node: DecisionNode | DecisionLeaf) -> int:
        from src.rules.service import DecisionLeaf, DecisionNode

        if isinstance(node, DecisionLeaf):
            return 1
        elif isinstance(node, DecisionNode):
            count = 1
            if node.true_branch:
                count += self._count_tree_nodes(node.true_branch)
            if node.false_branch:
                count += self._count_tree_nodes(node.false_branch)
            return count
        return 0

    def _periods_overlap(
        self,
        start1: date | None,
        end1: date | None,
        start2: date | None,
        end2: date | None,
    ) -> tuple[bool, date | None, date | None]:
        s1 = start1 or self.MIN_DATE
        e1 = end1 or self.MAX_DATE
        s2 = start2 or self.MIN_DATE
        e2 = end2 or self.MAX_DATE

        overlap_start = max(s1, s2)
        overlap_end = min(e1, e2)
        overlaps = overlap_start <= overlap_end

        return (
            overlaps,
            overlap_start if overlaps else None,
            overlap_end if overlaps else None,
        )


# =============================================================================
# Module-Level Convenience Functions
# =============================================================================


def check_cross_rule_consistency(rule: Rule, related_rules: list[Rule] | None = None) -> list[ConsistencyEvidence]:
    """Run all 3 cross-rule checks (contradiction, hierarchy, temporal)."""
    checker = CrossRuleChecker(related_rules=related_rules)
    return checker.check_all(rule)


def check_contradiction(rule: Rule, related_rules: list[Rule] | None = None) -> ConsistencyEvidence:
    return CrossRuleChecker(related_rules=related_rules).check_contradiction(rule)


def check_hierarchy(rule: Rule, related_rules: list[Rule] | None = None) -> ConsistencyEvidence:
    return CrossRuleChecker(related_rules=related_rules).check_hierarchy(rule)


def check_temporal_consistency(rule: Rule, related_rules: list[Rule] | None = None) -> ConsistencyEvidence:
    return CrossRuleChecker(related_rules=related_rules).check_temporal_consistency(rule)

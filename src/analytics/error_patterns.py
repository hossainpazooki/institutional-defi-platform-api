"""Error pattern analysis for rule consistency.

Analyzes consistency evidence across rules to identify systematic issues
and prioritize rules for human review.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.rules.service import (
    ConsistencyEvidence,
    ConsistencyStatus,
    Rule,
    RuleLoader,
)


@dataclass
class CategoryStats:
    """Statistics for a single check category."""

    category: str
    total: int = 0
    pass_count: int = 0
    warning_count: int = 0
    fail_count: int = 0
    avg_score: float = 0.0
    affected_rules: list[str] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return self.pass_count / self.total if self.total > 0 else 0.0

    @property
    def fail_rate(self) -> float:
        return self.fail_count / self.total if self.total > 0 else 0.0

    @property
    def warning_rate(self) -> float:
        return self.warning_count / self.total if self.total > 0 else 0.0


@dataclass
class ErrorPattern:
    """Detected error pattern across rules."""

    pattern_id: str
    category: str
    description: str
    severity: str  # "high", "medium", "low"
    affected_rule_count: int
    affected_rules: list[str]
    sample_evidence: list[ConsistencyEvidence]
    recommendation: str


@dataclass
class ReviewQueueItem:
    """Item in the review queue."""

    rule_id: str
    priority: float  # Higher = more urgent
    status: ConsistencyStatus
    confidence: float
    last_verified: str | None
    issues: list[str]


class ErrorPatternAnalyzer:
    """Analyzes error patterns across rules.

    Aggregates consistency evidence to identify:
    - Systematic issues (same error type across many rules)
    - High-priority rules for review
    - Category-level statistics
    """

    def __init__(self, rule_loader: RuleLoader | None = None) -> None:
        self._rule_loader = rule_loader
        self._evidence_cache: dict[str, list[ConsistencyEvidence]] = {}

    def analyze_rules(
        self,
        rules: list[Rule] | None = None,
    ) -> dict[str, CategoryStats]:
        """Analyze consistency evidence across rules."""
        if rules is None:
            if self._rule_loader is None:
                return {}
            rules = self._rule_loader.get_all_rules()

        category_stats: dict[str, CategoryStats] = {}

        for rule in rules:
            if not rule.consistency:
                continue

            for evidence in rule.consistency.evidence:
                cat = evidence.category

                if cat not in category_stats:
                    category_stats[cat] = CategoryStats(category=cat)

                stats = category_stats[cat]
                stats.total += 1

                if evidence.label == "pass":
                    stats.pass_count += 1
                elif evidence.label == "warning":
                    stats.warning_count += 1
                    stats.affected_rules.append(rule.rule_id)
                elif evidence.label == "fail":
                    stats.fail_count += 1
                    stats.affected_rules.append(rule.rule_id)

                stats.avg_score = (stats.avg_score * (stats.total - 1) + evidence.score) / stats.total

        for stats in category_stats.values():
            stats.affected_rules = list(set(stats.affected_rules))

        return category_stats

    def build_error_matrix(
        self,
        rules: list[Rule] | None = None,
    ) -> dict[str, dict[str, int]]:
        """Build confusion-like matrix of category x outcome."""
        if rules is None:
            if self._rule_loader is None:
                return {}
            rules = self._rule_loader.get_all_rules()

        matrix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

        for rule in rules:
            if not rule.consistency:
                continue

            for evidence in rule.consistency.evidence:
                matrix[evidence.category][evidence.label] += 1

        return {cat: dict(outcomes) for cat, outcomes in matrix.items()}

    def detect_patterns(
        self,
        rules: list[Rule] | None = None,
        min_affected: int = 2,
    ) -> list[ErrorPattern]:
        """Detect systematic error patterns."""
        if rules is None:
            if self._rule_loader is None:
                return []
            rules = self._rule_loader.get_all_rules()

        patterns = []
        category_stats = self.analyze_rules(rules)

        for category, stats in category_stats.items():
            if stats.fail_count >= min_affected:
                patterns.append(
                    ErrorPattern(
                        pattern_id=f"high_fail_{category}",
                        category=category,
                        description=f"High failure rate for {category} checks",
                        severity="high" if stats.fail_rate > 0.3 else "medium",
                        affected_rule_count=stats.fail_count,
                        affected_rules=stats.affected_rules[:10],
                        sample_evidence=self._get_sample_evidence(rules, category, "fail"),
                        recommendation=self._get_recommendation(category, "fail"),
                    )
                )

            if stats.warning_count >= min_affected and stats.warning_rate > 0.2:
                patterns.append(
                    ErrorPattern(
                        pattern_id=f"high_warning_{category}",
                        category=category,
                        description=f"Frequent warnings for {category} checks",
                        severity="medium" if stats.warning_rate > 0.3 else "low",
                        affected_rule_count=stats.warning_count,
                        affected_rules=stats.affected_rules[:10],
                        sample_evidence=self._get_sample_evidence(rules, category, "warning"),
                        recommendation=self._get_recommendation(category, "warning"),
                    )
                )

            if stats.avg_score < 0.6 and stats.total >= min_affected:
                patterns.append(
                    ErrorPattern(
                        pattern_id=f"low_score_{category}",
                        category=category,
                        description=f"Low average score ({stats.avg_score:.2f}) for {category}",
                        severity="medium",
                        affected_rule_count=stats.total,
                        affected_rules=stats.affected_rules[:10],
                        sample_evidence=self._get_sample_evidence(rules, category, None),
                        recommendation=f"Review {category} checks across all rules",
                    )
                )

        return sorted(
            patterns,
            key=lambda p: (
                {"high": 0, "medium": 1, "low": 2}[p.severity],
                -p.affected_rule_count,
            ),
        )

    def build_review_queue(
        self,
        rules: list[Rule] | None = None,
        max_items: int = 50,
    ) -> list[ReviewQueueItem]:
        """Build prioritized review queue."""
        if rules is None:
            if self._rule_loader is None:
                return []
            rules = self._rule_loader.get_all_rules()

        queue = []

        for rule in rules:
            if not rule.consistency:
                queue.append(
                    ReviewQueueItem(
                        rule_id=rule.rule_id,
                        priority=100.0,
                        status=ConsistencyStatus.UNVERIFIED,
                        confidence=0.0,
                        last_verified=None,
                        issues=["Rule has no consistency verification"],
                    )
                )
                continue

            summary = rule.consistency.summary
            evidence = rule.consistency.evidence

            status_priority = {
                ConsistencyStatus.INCONSISTENT: 100,
                ConsistencyStatus.NEEDS_REVIEW: 75,
                ConsistencyStatus.UNVERIFIED: 50,
                ConsistencyStatus.VERIFIED: 0,
            }

            priority = status_priority.get(summary.status, 50)
            priority += (1 - summary.confidence) * 20

            issues = []
            for ev in evidence:
                if ev.label == "fail":
                    issues.append(f"[FAIL] {ev.category}: {ev.details[:50]}")
                elif ev.label == "warning":
                    issues.append(f"[WARN] {ev.category}: {ev.details[:50]}")

            if issues or summary.status in (
                ConsistencyStatus.INCONSISTENT,
                ConsistencyStatus.NEEDS_REVIEW,
                ConsistencyStatus.UNVERIFIED,
            ):
                queue.append(
                    ReviewQueueItem(
                        rule_id=rule.rule_id,
                        priority=priority,
                        status=summary.status,
                        confidence=summary.confidence,
                        last_verified=summary.last_verified,
                        issues=issues[:5],
                    )
                )

        queue.sort(key=lambda x: x.priority, reverse=True)
        return queue[:max_items]

    def get_summary_stats(
        self,
        rules: list[Rule] | None = None,
    ) -> dict:
        """Get summary statistics across all rules."""
        if rules is None:
            if self._rule_loader is None:
                return {}
            rules = self._rule_loader.get_all_rules()

        total_rules = len(rules)
        verified = 0
        needs_review = 0
        inconsistent = 0
        unverified = 0
        total_evidence = 0
        total_score = 0.0

        for rule in rules:
            if not rule.consistency:
                unverified += 1
                continue

            status = rule.consistency.summary.status
            if status == ConsistencyStatus.VERIFIED:
                verified += 1
            elif status == ConsistencyStatus.NEEDS_REVIEW:
                needs_review += 1
            elif status == ConsistencyStatus.INCONSISTENT:
                inconsistent += 1
            else:
                unverified += 1

            for ev in rule.consistency.evidence:
                total_evidence += 1
                total_score += ev.score

        avg_score = total_score / total_evidence if total_evidence > 0 else 0.0

        return {
            "total_rules": total_rules,
            "verified": verified,
            "needs_review": needs_review,
            "inconsistent": inconsistent,
            "unverified": unverified,
            "verification_rate": (verified + needs_review) / total_rules if total_rules > 0 else 0.0,
            "average_score": round(avg_score, 4),
            "total_evidence": total_evidence,
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }

    def _get_sample_evidence(
        self,
        rules: list[Rule],
        category: str,
        label: str | None,
    ) -> list[ConsistencyEvidence]:
        """Get sample evidence for a category/label combination."""
        samples = []

        for rule in rules:
            if not rule.consistency:
                continue

            for ev in rule.consistency.evidence:
                if ev.category == category and (label is None or ev.label == label):
                    samples.append(ev)
                    if len(samples) >= 3:
                        return samples

        return samples

    def _get_recommendation(self, category: str, label: str) -> str:
        """Get recommendation for a category/label issue."""
        recommendations = {
            ("required_fields", "fail"): "Ensure all rules have rule_id and source fields",
            ("source_exists", "fail"): "Verify source document references are correct",
            ("source_exists", "warning"): "Add missing documents to the document registry",
            ("date_consistency", "fail"): "Fix effective date ranges (from <= to)",
            ("id_format", "warning"): "Rename rule IDs to follow snake_case convention",
            ("decision_tree_valid", "warning"): "Add decision trees to rules",
            ("deontic_alignment", "warning"): "Review deontic verb usage vs rule modality",
            ("deontic_alignment", "fail"): "Source and rule modality mismatch - major issue",
            ("actor_mentioned", "warning"): "Verify actor types match source text",
            ("instrument_mentioned", "warning"): "Verify instrument types match source text",
            ("keyword_overlap", "warning"): "Improve rule descriptions to match source terminology",
            ("negation_consistency", "warning"): "Check negation handling in conditions",
            ("exception_coverage", "warning"): "Add branches for exceptions mentioned in source",
        }

        return recommendations.get(
            (category, label),
            f"Review {category} checks and update rules as needed",
        )

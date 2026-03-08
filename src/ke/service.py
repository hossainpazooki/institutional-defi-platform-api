"""KE service — thin orchestration layer delegating to domain services.

The KE workbench coordinates rules, verification, analytics, and RAG
without duplicating their logic.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from src.analytics.drift import DriftDetector
from src.analytics.error_patterns import ErrorPatternAnalyzer
from src.analytics.utils import (
    build_corpus_rule_links,
    build_decision_trace_tree,
    build_decision_tree_structure,
    build_ontology_tree,
    build_rulebook_outline,
    is_supertree_available,
    render_corpus_links_html,
    render_decision_trace_html,
    render_ontology_tree_html,
    render_rulebook_outline_html,
)
from src.ontology.scenario import Scenario
from src.rag.rule_context import RuleContextRetriever
from src.rules.service import (
    ConsistencyBlock,
    ConsistencyEvidence,
    ConsistencyStatus,
    ConsistencySummary,
    DecisionEngine,
    RuleLoader,
)
from src.verification.service import ConsistencyEngine


class KEService:
    """Knowledge Engineering workbench service.

    Lazily initializes domain services and delegates operations to them.
    """

    def __init__(self, rules_dir: str | None = None) -> None:
        self._rules_dir = rules_dir
        self._rule_loader: RuleLoader | None = None
        self._consistency_engine: ConsistencyEngine | None = None
        self._analyzer: ErrorPatternAnalyzer | None = None
        self._drift_detector: DriftDetector | None = None
        self._context_retriever: RuleContextRetriever | None = None

    @property
    def rule_loader(self) -> RuleLoader:
        if self._rule_loader is None:
            if self._rules_dir:
                self._rule_loader = RuleLoader(self._rules_dir)
            else:
                from src.config import get_settings

                settings = get_settings()
                self._rule_loader = RuleLoader(settings.rules_dir)
            self._rule_loader.load_directory()
        return self._rule_loader

    @property
    def consistency_engine(self) -> ConsistencyEngine:
        if self._consistency_engine is None:
            self._consistency_engine = ConsistencyEngine()
        return self._consistency_engine

    @property
    def analyzer(self) -> ErrorPatternAnalyzer:
        if self._analyzer is None:
            self._analyzer = ErrorPatternAnalyzer(rule_loader=self.rule_loader)
        return self._analyzer

    @property
    def drift_detector(self) -> DriftDetector:
        if self._drift_detector is None:
            self._drift_detector = DriftDetector(rule_loader=self.rule_loader)
        return self._drift_detector

    @property
    def context_retriever(self) -> RuleContextRetriever:
        if self._context_retriever is None:
            self._context_retriever = RuleContextRetriever(rule_loader=self.rule_loader)
        return self._context_retriever

    # =========================================================================
    # Verification
    # =========================================================================

    def verify_rule(self, rule_id: str, source_text: str | None = None, tiers: list[int] | None = None) -> dict[str, Any] | None:
        """Verify a single rule's consistency."""
        tiers = tiers or [0, 1]
        rule = self.rule_loader.get_rule(rule_id)
        if rule is None:
            return None

        result = self.consistency_engine.verify_rule(rule=rule, source_text=source_text, tiers=tiers)
        return {
            "rule_id": rule_id,
            "status": result.summary.status.value,
            "confidence": result.summary.confidence,
            "evidence_count": len(result.evidence),
            "evidence": [
                {
                    "tier": ev.tier,
                    "category": ev.category,
                    "label": ev.label,
                    "score": ev.score,
                    "details": ev.details,
                }
                for ev in result.evidence
            ],
        }

    def verify_all_rules(self, tiers: list[int] | None = None, save: bool = False) -> dict[str, Any]:
        """Verify all loaded rules."""
        tiers = tiers or [0, 1]
        rules = self.rule_loader.get_all_rules()

        results = []
        for rule in rules:
            consistency = self.consistency_engine.verify_rule(rule, tiers=tiers)
            results.append(
                {
                    "rule_id": rule.rule_id,
                    "status": consistency.summary.status.value,
                    "confidence": consistency.summary.confidence,
                }
            )
            if save:
                rule.consistency = consistency

        return {
            "total": len(results),
            "verified": sum(1 for r in results if r["status"] == "verified"),
            "needs_review": sum(1 for r in results if r["status"] == "needs_review"),
            "inconsistent": sum(1 for r in results if r["status"] == "inconsistent"),
            "results": results,
        }

    # =========================================================================
    # Analytics
    # =========================================================================

    def get_analytics_summary(self) -> dict[str, Any]:
        """Get summary statistics for all rules."""
        return self.analyzer.get_summary_stats()

    def get_error_patterns(self, min_affected: int = 2) -> list[Any]:
        """Detect error patterns across rules."""
        return self.analyzer.detect_patterns(min_affected=min_affected)

    def get_error_matrix(self) -> dict[str, dict[str, int]]:
        """Get error confusion matrix."""
        return self.analyzer.build_error_matrix()

    def get_review_queue(self, max_items: int = 50) -> list[Any]:
        """Get prioritized review queue."""
        return self.analyzer.build_review_queue(max_items=max_items)

    # =========================================================================
    # Drift Detection
    # =========================================================================

    def set_drift_baseline(self) -> dict[str, Any]:
        """Set current state as drift baseline."""
        metrics = self.drift_detector.set_baseline()
        return {
            "message": "Baseline set",
            "timestamp": metrics.timestamp,
            "total_rules": metrics.total_rules,
            "avg_confidence": metrics.avg_confidence,
        }

    def detect_drift(self) -> Any:
        """Detect drift from baseline."""
        return self.drift_detector.detect_drift()

    def get_drift_history(self, window: int = 10) -> list[Any]:
        """Get metrics history."""
        return self.drift_detector.get_history()[-window:]

    def get_author_comparison(self) -> dict[str, Any]:
        """Compare consistency metrics by author."""
        return self.drift_detector.compare_authors()

    # =========================================================================
    # Rule Context
    # =========================================================================

    def get_rule_context(self, rule_id: str) -> dict[str, Any] | None:
        """Get source context for a rule."""
        rule = self.rule_loader.get_rule(rule_id)
        if rule is None:
            return None

        context = self.context_retriever.get_rule_context(rule)
        return {
            "rule_id": context.rule_id,
            "source_passages": [
                {"text": p.text[:200], "score": p.score, "document_id": p.document_id} for p in context.source_passages
            ],
            "cross_references": context.cross_references,
            "related_rules": context.related_rules,
        }

    def get_related_rules(self, rule_id: str, top_k: int = 5) -> list[dict[str, Any]] | None:
        """Get rules related to a given rule."""
        rule = self.rule_loader.get_rule(rule_id)
        if rule is None:
            return None

        related = self.context_retriever.find_related_rules(rule, top_k=top_k)
        return [
            {
                "rule_id": r.rule_id,
                "description": r.description,
                "source": {
                    "document_id": r.source.document_id if r.source else None,
                    "article": r.source.article if r.source else None,
                }
                if r.source
                else None,
                "tags": r.tags,
            }
            for r in related
        ]

    # =========================================================================
    # Human Review
    # =========================================================================

    def submit_human_review(self, rule_id: str, label: str, notes: str, reviewer_id: str) -> dict[str, Any] | None:
        """Submit a human review (Tier 4) for a rule."""
        rule = self.rule_loader.get_rule(rule_id)
        if rule is None:
            return None

        timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        score = {"consistent": 1.0, "inconsistent": 0.0, "unknown": 0.5}.get(label, 0.5)

        human_evidence = ConsistencyEvidence(
            tier=4,
            category="human_review",
            label="pass" if label == "consistent" else ("fail" if label == "inconsistent" else "warning"),
            score=score,
            details=f"Human review by {reviewer_id}: {notes}",
            rule_element="__rule__",
            timestamp=timestamp,
        )

        existing_evidence = list(rule.consistency.evidence) if rule.consistency else []
        existing_evidence.append(human_evidence)

        new_status = {
            "consistent": ConsistencyStatus.VERIFIED,
            "inconsistent": ConsistencyStatus.INCONSISTENT,
            "unknown": ConsistencyStatus.NEEDS_REVIEW,
        }.get(label, ConsistencyStatus.NEEDS_REVIEW)

        if rule.consistency:
            existing_conf = rule.consistency.summary.confidence
            new_confidence = (0.4 * existing_conf) + (0.6 * score)
        else:
            new_confidence = score

        new_summary = ConsistencySummary(
            status=new_status,
            confidence=round(new_confidence, 4),
            last_verified=timestamp,
            verified_by=f"human:{reviewer_id}",
            notes=notes,
        )

        rule.consistency = ConsistencyBlock(summary=new_summary, evidence=existing_evidence)

        return {
            "rule_id": rule_id,
            "status": new_status.value,
            "confidence": new_confidence,
            "review_tier": 4,
            "reviewer_id": reviewer_id,
            "message": f"Human review submitted. Status updated to {new_status.value}.",
        }

    def get_rule_reviews(self, rule_id: str) -> list[dict[str, Any]] | None:
        """Get all human reviews for a rule."""
        rule = self.rule_loader.get_rule(rule_id)
        if rule is None:
            return None

        if not rule.consistency:
            return []

        return [
            {
                "tier": ev.tier,
                "category": ev.category,
                "label": ev.label,
                "score": ev.score,
                "details": ev.details,
                "timestamp": ev.timestamp,
            }
            for ev in rule.consistency.evidence
            if ev.tier == 4 and ev.category == "human_review"
        ]

    # =========================================================================
    # Charts
    # =========================================================================

    def get_supertree_status(self) -> dict[str, Any]:
        """Check if Supertree visualization is available."""
        available = is_supertree_available()
        return {
            "available": available,
            "message": (
                "Supertree is available for interactive charts"
                if available
                else "Install supertree for interactive charts: pip install -r requirements-visualization.txt"
            ),
        }

    def get_rulebook_outline(self) -> dict[str, Any]:
        """Get rulebook outline tree data."""
        rules = self.rule_loader.get_all_rules()
        return build_rulebook_outline(rules)

    def render_rulebook_outline(self) -> str:
        """Render rulebook outline as HTML."""
        rules = self.rule_loader.get_all_rules()
        tree_data = build_rulebook_outline(rules)
        return render_rulebook_outline_html(tree_data)

    def get_ontology_tree(self) -> dict[str, Any]:
        """Get ontology tree data."""
        return build_ontology_tree()

    def render_ontology_tree(self) -> str:
        """Render ontology tree as HTML."""
        tree_data = build_ontology_tree()
        return render_ontology_tree_html(tree_data)

    def get_corpus_links(self) -> dict[str, Any]:
        """Get corpus-to-rule links tree data."""
        rules = self.rule_loader.get_all_rules()
        return build_corpus_rule_links(rules)

    def render_corpus_links(self) -> str:
        """Render corpus-to-rule links as HTML."""
        rules = self.rule_loader.get_all_rules()
        tree_data = build_corpus_rule_links(rules)
        return render_corpus_links_html(tree_data)

    def get_decision_tree(self, rule_id: str) -> dict[str, Any] | None:
        """Get decision tree structure for a rule."""
        rule = self.rule_loader.get_rule(rule_id)
        if rule is None:
            return None
        if rule.decision_tree is None:
            return {"error": "no_decision_tree"}
        return build_decision_tree_structure(rule.decision_tree)

    def get_decision_trace(self, rule_id: str, scenario_dict: dict[str, Any]) -> dict[str, Any] | None:
        """Evaluate rule and return decision trace tree data."""
        rule = self.rule_loader.get_rule(rule_id)
        if rule is None:
            return None

        scenario = Scenario(**scenario_dict)
        engine = DecisionEngine(self.rule_loader)
        result = engine.evaluate(scenario, rule_id)

        return build_decision_trace_tree(
            trace=result.trace,
            decision=result.decision,
            rule_id=rule_id,
        )

    def render_decision_trace(self, rule_id: str, scenario_dict: dict[str, Any]) -> str | None:
        """Evaluate rule and return decision trace as HTML."""
        tree_data = self.get_decision_trace(rule_id, scenario_dict)
        if tree_data is None:
            return None
        return render_decision_trace_html(tree_data)

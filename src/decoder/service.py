"""Decoder Service - transforms decisions into tiered explanations and counterfactual analysis."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, cast

from .constants import ARTICLE_PATTERNS, DEFAULT_TEMPLATES, FRAMEWORK_METADATA, RISK_LEVELS
from .schemas import (
    AuditInfo,
    Citation,
    ComparisonMatrix,
    CounterfactualExplanation,
    CounterfactualResponse,
    DecoderResponse,
    DeltaAnalysis,
    Explanation,
    ExplanationSummary,
    ExplanationTemplate,
    ExplanationTier,
    MatrixInsight,
    OutcomeSummary,
    Scenario,
    ScenarioType,
)

if TYPE_CHECKING:
    from src.rules.service import DecisionEngine, DecisionResult


# =============================================================================
# Citation Injector
# =============================================================================


class CitationInjector:
    """Retrieves and enriches regulatory citations."""

    def __init__(self, retriever: Any = None) -> None:
        """Initialize with optional RAG retriever."""
        self._retriever = retriever

    @property
    def retriever(self) -> Any:
        """Lazy-load RAG retriever."""
        if self._retriever is None:
            try:
                from src.rag.service import Retriever

                self._retriever = Retriever()
            except ImportError:
                pass
        return self._retriever

    def get_citations(
        self,
        rule_id: str,
        framework: str,
        activity_type: str | None = None,
        max_citations: int = 5,
    ) -> list[Citation]:
        """Retrieve relevant citations for a rule."""
        citations: list[Citation] = []

        # Try RAG-based retrieval first
        if self.retriever:
            rag_citations = self._retrieve_from_rag(rule_id, framework, activity_type, max_citations)
            citations.extend(rag_citations)

        # Fall back to pattern-based citations
        if len(citations) < max_citations:
            pattern_citations = self._get_pattern_citations(
                rule_id, framework, activity_type, max_citations - len(citations)
            )
            citations.extend(pattern_citations)

        # Enrich with metadata
        citations = [self._enrich_citation(c) for c in citations]
        return citations[:max_citations]

    def get_citation_by_reference(self, framework: str, reference: str) -> Citation | None:
        """Get a specific citation by reference."""
        meta = cast("dict[str, Any]", FRAMEWORK_METADATA.get(framework, {}))
        citation = Citation(
            framework=framework,
            reference=reference,
            full_reference=f"{meta.get('regulation_id', framework)}, {reference}",
            text=f"Reference to {reference}",
            url=meta.get("url_base"),
            effective_date=meta.get("effective_date"),
            relevance="supporting",
        )
        return self._enrich_citation(citation)

    def _retrieve_from_rag(
        self, rule_id: str, framework: str, activity_type: str | None, max_results: int
    ) -> list[Citation]:
        """Retrieve citations using RAG service."""
        if not self.retriever:
            return []

        citations = []
        try:
            query_parts = [framework, rule_id]
            if activity_type:
                query_parts.append(activity_type)
            query = " ".join(query_parts)

            results: list[dict[str, Any]] = self.retriever.search(query, top_k=max_results)
            for result in results:
                citation = Citation(
                    framework=framework,
                    reference=result.get("reference", ""),
                    full_reference=result.get("full_reference", ""),
                    text=result.get("text", result.get("content", "")),
                    url=result.get("url"),
                    relevance_score=result.get("score", 0.0),
                    relevance=self._score_to_relevance(result.get("score", 0.0)),  # type: ignore[arg-type]
                )
                citations.append(citation)
        except Exception:
            pass
        return citations

    def _get_pattern_citations(
        self, rule_id: str, framework: str, activity_type: str | None, max_results: int
    ) -> list[Citation]:
        """Get citations based on known patterns."""
        citations: list[Citation] = []
        patterns = ARTICLE_PATTERNS.get(framework, {})
        categories = self._extract_categories(rule_id, activity_type)

        for category in categories:
            if category in patterns:
                for ref in patterns[category]:
                    if len(citations) >= max_results:
                        break
                    meta = cast("dict[str, Any]", FRAMEWORK_METADATA.get(framework, {}))
                    citation = Citation(
                        framework=framework,
                        reference=ref,
                        full_reference=f"{meta.get('regulation_id', framework)}, {ref}",
                        text=f"{category.replace('_', ' ').title()} provision",
                        url=meta.get("url_base"),
                        effective_date=meta.get("effective_date"),
                        relevance="supporting",
                    )
                    citations.append(citation)
        return citations

    def _extract_categories(self, rule_id: str, activity_type: str | None) -> list[str]:
        """Extract citation categories from rule ID and activity."""
        categories = []
        rule_lower = rule_id.lower()

        category_patterns = {
            "authorization": ["auth", "license", "register"],
            "stablecoin": ["stablecoin", "emt", "art_"],
            "exemptions": ["exempt", "waiver"],
            "definitions": ["definition", "scope"],
            "casp": ["casp", "service_provider"],
            "custody": ["custody", "safekeep"],
        }

        for category, pattern_list in category_patterns.items():
            if any(p in rule_lower for p in pattern_list):
                categories.append(category)

        if activity_type:
            activity_map = {
                "public_offer": "authorization",
                "custody": "custody",
                "trading": "casp",
                "swap": "casp",
            }
            if activity_type in activity_map:
                cat = activity_map[activity_type]
                if cat not in categories:
                    categories.append(cat)

        if not categories:
            categories.append("definitions")
        return categories

    def _enrich_citation(self, citation: Citation) -> Citation:
        """Enrich citation with framework metadata."""
        meta = cast("dict[str, Any]", FRAMEWORK_METADATA.get(citation.framework, {}))

        if not citation.full_reference or citation.full_reference == citation.reference:
            reg_id = meta.get("regulation_id", citation.framework)
            citation.full_reference = f"{reg_id}, {citation.reference}"

        if not citation.url:
            citation.url = meta.get("url_base")
        if not citation.effective_date:
            citation.effective_date = meta.get("effective_date")
        return citation

    def _score_to_relevance(self, score: float) -> str:
        """Convert relevance score to category."""
        if score >= 0.8:
            return "primary"
        elif score >= 0.5:
            return "supporting"
        return "contextual"


# =============================================================================
# Template Registry
# =============================================================================


class TemplateRegistry:
    """Registry for explanation templates."""

    def __init__(self) -> None:
        """Initialize with default templates."""
        self._templates: dict[str, ExplanationTemplate] = {}
        self._load_defaults()

    def _load_defaults(self) -> None:
        """Load default templates."""
        for template in DEFAULT_TEMPLATES:
            self.register(template)

    def register(self, template: ExplanationTemplate) -> None:
        """Register a template."""
        self._templates[template.id] = template

    def get(self, template_id: str) -> ExplanationTemplate | None:
        """Get template by ID."""
        return self._templates.get(template_id)

    def list_templates(self) -> list[ExplanationTemplate]:
        """List all registered templates."""
        return list(self._templates.values())

    def select(self, activity_type: str, framework: str, outcome: str) -> ExplanationTemplate | None:
        """Select best matching template."""
        candidates: list[tuple[int, ExplanationTemplate]] = []

        for template in self._templates.values():
            score = self._calculate_match_score(template, activity_type, framework, outcome)
            if score > 0:
                candidates.append((score, template))

        if not candidates:
            return self._templates.get("generic_fallback")

        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    def _calculate_match_score(
        self, template: ExplanationTemplate, activity_type: str, framework: str, outcome: str
    ) -> int:
        """Calculate how well a template matches criteria."""
        score = 0

        if template.outcome != outcome:
            return 0

        if framework in template.frameworks:
            score += 10
        elif "Unknown" in template.frameworks:
            score += 1

        if activity_type in template.activity_types:
            score += 5
        elif "general" in template.activity_types:
            score += 1

        return score

    def render_template(
        self, template: ExplanationTemplate, tier: ExplanationTier, variables: dict[str, str]
    ) -> dict[str, str]:
        """Render a template with variables."""
        sections = template.tiers.get(tier, [])
        result: dict[str, str] = {}

        for section in sections:
            rendered = section.template
            for var_name, var_value in variables.items():
                placeholder = "{{" + var_name + "}}"
                rendered = rendered.replace(placeholder, str(var_value))
            result[section.type] = rendered

        return result


# =============================================================================
# Delta Analyzer
# =============================================================================


class DeltaAnalyzer:
    """Analyzes differences between baseline and counterfactual outcomes."""

    def compare(self, baseline: OutcomeSummary, counterfactual: OutcomeSummary) -> DeltaAnalysis:
        """Compare baseline and counterfactual outcomes."""
        delta = DeltaAnalysis()

        delta.status_from = baseline.status
        delta.status_to = counterfactual.status
        delta.status_changed = baseline.status != counterfactual.status

        delta.framework_changed = baseline.framework != counterfactual.framework
        if delta.framework_changed:
            delta.frameworks_removed = [baseline.framework]
            delta.frameworks_added = [counterfactual.framework]

        delta.risk_delta = self._calculate_risk_delta(baseline.risk_level, counterfactual.risk_level)
        if delta.risk_delta > 0:
            delta.risk_factors_added = self._infer_risk_factors(baseline, counterfactual, increasing=True)
        elif delta.risk_delta < 0:
            delta.risk_factors_removed = self._infer_risk_factors(baseline, counterfactual, increasing=False)

        baseline_conditions = set(baseline.conditions)
        counterfactual_conditions = set(counterfactual.conditions)

        delta.new_requirements = list(counterfactual_conditions - baseline_conditions)
        delta.removed_requirements = list(baseline_conditions - counterfactual_conditions)
        delta.modified_requirements = self._find_modified_requirements(baseline.conditions, counterfactual.conditions)

        return delta

    def _calculate_risk_delta(self, from_risk: str, to_risk: str) -> int:
        """Calculate risk level change."""
        try:
            from_idx = RISK_LEVELS.index(from_risk)
            to_idx = RISK_LEVELS.index(to_risk)
            return to_idx - from_idx
        except ValueError:
            return 0

    def _infer_risk_factors(
        self, baseline: OutcomeSummary, counterfactual: OutcomeSummary, increasing: bool
    ) -> list[str]:
        """Infer what risk factors changed."""
        factors = []

        if baseline.status != counterfactual.status:
            if increasing:
                factors.append(f"Status changed from {baseline.status} to {counterfactual.status}")
            else:
                factors.append(f"Status improved from {baseline.status} to {counterfactual.status}")

        if baseline.framework != counterfactual.framework:
            if increasing:
                factors.append(f"Now subject to {counterfactual.framework} requirements")
            else:
                factors.append(f"No longer subject to {baseline.framework} requirements")

        new_conditions = set(counterfactual.conditions) - set(baseline.conditions)
        if new_conditions and increasing:
            factors.append(f"{len(new_conditions)} new condition(s) required")

        removed_conditions = set(baseline.conditions) - set(counterfactual.conditions)
        if removed_conditions and not increasing:
            factors.append(f"{len(removed_conditions)} condition(s) no longer required")

        return factors

    def _find_modified_requirements(
        self, baseline_conditions: list[str], counterfactual_conditions: list[str]
    ) -> list[dict[str, str]]:
        """Find requirements that were modified."""
        modified = []

        def extract_keywords(condition: str) -> set[str]:
            words = condition.lower().replace(",", " ").replace(".", " ").split()
            stopwords = {"the", "a", "an", "is", "are", "to", "of", "for", "and", "or", "in", "on"}
            return {w for w in words if len(w) > 2 and w not in stopwords}

        baseline_keywords = [(c, extract_keywords(c)) for c in baseline_conditions]
        cf_keywords = [(c, extract_keywords(c)) for c in counterfactual_conditions]

        for b_cond, b_keys in baseline_keywords:
            for cf_cond, cf_keys in cf_keywords:
                if b_cond == cf_cond:
                    continue

                overlap = b_keys & cf_keys
                if len(overlap) >= 2 and len(overlap) >= len(b_keys) * 0.5:
                    modified.append(
                        {
                            "requirement": " ".join(overlap)[:50],
                            "baseline": b_cond,
                            "counterfactual": cf_cond,
                            "change": "modified",
                        }
                    )

        return modified

    def summarize_impact(self, delta: DeltaAnalysis) -> str:
        """Generate human-readable impact summary."""
        parts = []

        if delta.status_changed:
            parts.append(f"Status changes from {delta.status_from} to {delta.status_to}.")

        if delta.risk_delta > 0:
            parts.append(f"Risk increases by {delta.risk_delta} level(s).")
        elif delta.risk_delta < 0:
            parts.append(f"Risk decreases by {abs(delta.risk_delta)} level(s).")

        if delta.framework_changed:
            if delta.frameworks_added:
                parts.append(f"New framework applies: {', '.join(delta.frameworks_added)}.")
            if delta.frameworks_removed:
                parts.append(f"Previous framework no longer applies: {', '.join(delta.frameworks_removed)}.")

        if delta.new_requirements:
            parts.append(f"{len(delta.new_requirements)} new requirement(s) apply.")
        if delta.removed_requirements:
            parts.append(f"{len(delta.removed_requirements)} requirement(s) no longer apply.")

        if not parts:
            return "No significant changes detected."

        return " ".join(parts)

    def calculate_severity(self, delta: DeltaAnalysis) -> str:
        """Calculate overall severity of changes."""
        score = 0.0

        if delta.status_changed:
            status_severity = {
                ("APPROVED", "CONDITIONAL"): 1,
                ("APPROVED", "DENIED"): 3,
                ("CONDITIONAL", "DENIED"): 2,
                ("CONDITIONAL", "APPROVED"): -1,
                ("DENIED", "CONDITIONAL"): -1,
                ("DENIED", "APPROVED"): -2,
            }
            key = (delta.status_from, delta.status_to)
            score += status_severity.get(key, 0)

        score += delta.risk_delta
        score += len(delta.new_requirements) * 0.5
        score -= len(delta.removed_requirements) * 0.3

        if score >= 3:
            return "critical"
        elif score >= 1.5:
            return "high"
        elif score >= 0.5:
            return "medium"
        else:
            return "low"


# =============================================================================
# Decoder Service
# =============================================================================


class DecoderService:
    """Transforms decision results into tiered explanations."""

    def __init__(
        self,
        citation_injector: CitationInjector | None = None,
        template_registry: TemplateRegistry | None = None,
    ) -> None:
        """Initialize decoder with optional dependencies."""
        self._citations = citation_injector
        self._templates = template_registry

    @property
    def citations(self) -> CitationInjector:
        """Lazy-load citation injector."""
        if self._citations is None:
            self._citations = CitationInjector()
        return self._citations

    @property
    def templates(self) -> TemplateRegistry:
        """Lazy-load template registry."""
        if self._templates is None:
            self._templates = TemplateRegistry()
        return self._templates

    def explain(
        self,
        decision: DecisionResult,
        tier: ExplanationTier = ExplanationTier.INSTITUTIONAL,
        include_citations: bool = True,
    ) -> DecoderResponse:
        """Generate tiered explanation for a decision."""
        start_time = time.time()

        framework = self._extract_framework(decision)
        status = self._determine_status(decision)
        risk_level = self._assess_risk(decision)

        template = self.templates.select(
            activity_type=self._extract_activity(decision),
            framework=framework,
            outcome=self._map_outcome(status),
        )

        explanation = self._render_explanation(decision, template, tier)

        citations: list[Citation] = []
        if include_citations:
            citations = self.citations.get_citations(
                rule_id=decision.rule_id,
                framework=framework,
                max_citations=self._citation_limit_for_tier(tier),
            )

        processing_time = int((time.time() - start_time) * 1000)

        return DecoderResponse(
            decision_id=decision.rule_id,
            tier=tier,
            summary=ExplanationSummary(
                status=status,
                confidence=self._calculate_confidence(decision),
                primary_framework=framework,
                risk_level=risk_level,  # type: ignore[arg-type]
            ),
            explanation=explanation,
            citations=citations,
            audit=AuditInfo(
                trace_id=decision.rule_id,
                rules_evaluated=1,
                processing_time_ms=processing_time,
                template_id=template.id if template else None,
            ),
        )

    def explain_by_id(
        self,
        decision_id: str,
        tier: ExplanationTier = ExplanationTier.INSTITUTIONAL,
        include_citations: bool = True,
    ) -> DecoderResponse:
        """Generate explanation by decision ID."""
        return DecoderResponse(
            decision_id=decision_id,
            tier=tier,
            summary=ExplanationSummary(
                status="UNKNOWN",
                confidence=0.0,
                primary_framework="Unknown",
                risk_level="MEDIUM",
            ),
            explanation=Explanation(
                headline="Decision not found",
                body=f"Could not find decision with ID: {decision_id}",
                conditions=[],
                warnings=["Decision lookup not yet implemented"],
            ),
            citations=[],
            audit=AuditInfo(rules_evaluated=0),
        )

    def _extract_framework(self, decision: DecisionResult) -> str:
        """Extract regulatory framework from decision."""
        if decision.rule_metadata and decision.rule_metadata.source:
            doc_id = decision.rule_metadata.source.document_id
            if doc_id:
                framework_map = {
                    "mica": "MiCA",
                    "fca": "FCA",
                    "sec": "SEC",
                    "mas": "MAS",
                    "finma": "FINMA",
                }
                for key, name in framework_map.items():
                    if key in doc_id.lower():
                        return name
        return "Unknown"

    def _extract_activity(self, decision: DecisionResult) -> str:
        """Extract activity type from decision."""
        rule_id = decision.rule_id.lower()
        if "swap" in rule_id:
            return "swap"
        if "offer" in rule_id or "public_offer" in rule_id:
            return "public_offer"
        if "custody" in rule_id:
            return "custody"
        if "trading" in rule_id:
            return "trading"
        if "transfer" in rule_id:
            return "transfer"
        return "general"

    def _determine_status(self, decision: DecisionResult) -> str:
        """Determine compliance status from decision."""
        if not decision.applicable:
            return "NOT_APPLICABLE"

        outcome = (decision.decision or "").lower()
        if outcome in ("authorized", "compliant", "approved", "exempt"):
            return "APPROVED"
        if outcome in ("conditional", "requires_review", "pending"):
            return "CONDITIONAL"
        if outcome in ("not_authorized", "non_compliant", "denied", "prohibited"):
            return "DENIED"

        return "UNKNOWN"

    def _map_outcome(self, status: str) -> str:
        """Map status to template outcome category."""
        if status in ("APPROVED", "NOT_APPLICABLE"):
            return "compliant"
        if status == "CONDITIONAL":
            return "conditional"
        return "non_compliant"

    def _assess_risk(self, decision: DecisionResult) -> str:
        """Assess risk level from decision."""
        status = self._determine_status(decision)

        if status == "DENIED":
            return "HIGH"
        if status == "CONDITIONAL":
            return "MEDIUM"
        if status in ("APPROVED", "NOT_APPLICABLE"):
            return "LOW"

        if decision.trace:
            warning_count = sum(1 for step in decision.trace if not step.result)
            if warning_count > 2:
                return "MEDIUM"

        return "LOW"

    def _calculate_confidence(self, decision: DecisionResult) -> float:
        """Calculate confidence score for explanation."""
        base_confidence = 0.8

        if decision.rule_metadata and decision.rule_metadata.consistency:
            summary = decision.rule_metadata.consistency.summary
            if summary and summary.confidence:
                base_confidence = min(base_confidence, summary.confidence)

        status = self._determine_status(decision)
        if status == "CONDITIONAL":
            base_confidence *= 0.9
        elif status == "UNKNOWN":
            base_confidence *= 0.5

        return round(base_confidence, 2)

    def _citation_limit_for_tier(self, tier: ExplanationTier) -> int:
        """Get citation limit based on tier."""
        limits = {
            ExplanationTier.RETAIL: 0,
            ExplanationTier.PROTOCOL: 3,
            ExplanationTier.INSTITUTIONAL: 5,
            ExplanationTier.REGULATOR: 10,
        }
        return limits.get(tier, 3)

    def _render_explanation(self, decision: DecisionResult, template: ExplanationTemplate | None, tier: ExplanationTier) -> Explanation:
        """Render explanation using template and tier."""
        status = self._determine_status(decision)
        framework = self._extract_framework(decision)

        if tier == ExplanationTier.RETAIL:
            return self._render_retail(decision, status, framework)
        elif tier == ExplanationTier.PROTOCOL:
            return self._render_protocol(decision, status, framework)
        elif tier == ExplanationTier.INSTITUTIONAL:
            return self._render_institutional(decision, status, framework)
        else:
            return self._render_regulator(decision, status, framework)

    def _render_retail(self, decision: DecisionResult, status: str, framework: str) -> Explanation:
        """Render retail-tier explanation."""
        if status == "APPROVED":
            headline = "This activity is allowed."
            body = f"Based on {framework} regulations, this activity is compliant. No special requirements apply."
        elif status == "CONDITIONAL":
            headline = "This activity may be allowed with conditions."
            body = f"Under {framework} rules, this activity requires meeting certain conditions. Please review the requirements below."
        elif status == "DENIED":
            headline = "This activity is not allowed."
            body = f"{framework} regulations prohibit this activity in its current form. Consider restructuring or consulting a compliance advisor."
        else:
            headline = "Status could not be determined."
            body = "We couldn't determine the compliance status. Please consult an expert."

        return Explanation(
            headline=headline,
            body=body,
            conditions=[o.description or o.id for o in decision.obligations if o.description],
            warnings=[decision.notes] if decision.notes else [],
        )

    def _render_protocol(self, decision: DecisionResult, status: str, framework: str) -> Explanation:
        """Render protocol-tier explanation."""
        headline = f"Compliance Status: {status}"
        parts = [
            f"Framework: {framework}",
            f"Rule: {decision.rule_id}",
            f"Applicable: {decision.applicable}",
            f"Decision: {decision.decision or 'N/A'}",
        ]
        if decision.source:
            parts.append(f"Source: {decision.source}")

        body = " | ".join(parts)
        conditions = [f"{ob.id}: {ob.description}" if ob.description else ob.id for ob in decision.obligations]

        return Explanation(
            headline=headline,
            body=body,
            conditions=conditions,
            warnings=[decision.notes] if decision.notes else [],
        )

    def _render_institutional(self, decision: DecisionResult, status: str, framework: str) -> Explanation:
        """Render institutional-tier explanation."""
        headline = f"Compliance Status: {status}"
        lines = [
            f"**Regulatory Basis:** {framework}",
            f"**Rule ID:** {decision.rule_id}",
            f"**Applicability:** {'Yes' if decision.applicable else 'No'}",
            f"**Decision:** {decision.decision or 'Pending'}",
        ]

        if decision.source:
            lines.append(f"**Source Reference:** {decision.source}")

        if decision.rule_metadata:
            meta = decision.rule_metadata
            if meta.version:
                lines.append(f"**Rule Version:** {meta.version}")
            if meta.tags:
                lines.append(f"**Tags:** {', '.join(meta.tags)}")

        body = "\n".join(lines)

        conditions = []
        for ob in decision.obligations:
            cond_parts = [ob.id]
            if ob.description:
                cond_parts.append(ob.description)
            if ob.deadline:
                cond_parts.append(f"(Deadline: {ob.deadline})")
            conditions.append(" - ".join(cond_parts))

        warnings = []
        if decision.notes:
            warnings.append(decision.notes)
        for step in decision.trace:
            if not step.result and "warning" in step.condition.lower():
                warnings.append(f"Check failed: {step.condition}")

        return Explanation(headline=headline, body=body, conditions=conditions, warnings=warnings)

    def _render_regulator(self, decision: DecisionResult, status: str, framework: str) -> Explanation:
        """Render regulator-tier explanation."""
        headline = f"Regulatory Decision: {status}"
        lines = [
            "## Regulatory Framework",
            f"Primary Framework: {framework}",
            f"Rule Identifier: {decision.rule_id}",
            "",
            "## Decision Details",
            f"Applicability Determination: {'Applicable' if decision.applicable else 'Not Applicable'}",
            f"Compliance Outcome: {decision.decision or 'Under Review'}",
        ]

        if decision.source:
            lines.extend(["", "## Legal Basis", f"Source: {decision.source}"])

        if decision.rule_metadata:
            meta = decision.rule_metadata
            lines.extend(["", "## Rule Metadata", f"Version: {meta.version}"])
            if meta.source:
                if meta.source.article:
                    lines.append(f"Article: {meta.source.article}")
                if meta.source.section:
                    lines.append(f"Section: {meta.source.section}")

            if meta.consistency:
                lines.extend(
                    [
                        "",
                        "## Consistency Verification",
                        f"Status: {meta.consistency.summary.status if meta.consistency.summary else 'Unknown'}",
                    ]
                )

        if decision.trace:
            lines.extend(["", "## Evaluation Trace"])
            for i, step in enumerate(decision.trace, 1):
                result_str = "PASS" if step.result else "FAIL"
                lines.append(f"{i}. [{result_str}] {step.node}: {step.condition}")

        body = "\n".join(lines)

        conditions = []
        for ob in decision.obligations:
            parts = [f"**{ob.id}**"]
            if ob.description:
                parts.append(ob.description)
            if ob.source:
                parts.append(f"(Ref: {ob.source})")
            if ob.deadline:
                parts.append(f"[Deadline: {ob.deadline}]")
            conditions.append(" ".join(parts))

        warnings = [decision.notes] if decision.notes else []

        return Explanation(headline=headline, body=body, conditions=conditions, warnings=warnings)


# =============================================================================
# Counterfactual Engine
# =============================================================================


class CounterfactualEngine:
    """What-if analysis engine - evaluates scenario changes."""

    def __init__(
        self,
        decision_engine: DecisionEngine | None = None,
        decoder_service: DecoderService | None = None,
    ) -> None:
        """Initialize with optional dependencies."""
        self._decision_engine = decision_engine
        self._decoder = decoder_service
        self._delta_analyzer = DeltaAnalyzer()

    @property
    def decision_engine(self) -> DecisionEngine:
        """Lazy-load decision engine."""
        if self._decision_engine is None:
            from src.rules.service import DecisionEngine

            self._decision_engine = DecisionEngine()
        return self._decision_engine

    @property
    def decoder(self) -> DecoderService:
        """Lazy-load decoder service."""
        if self._decoder is None:
            self._decoder = DecoderService()
        return self._decoder

    def analyze(
        self,
        baseline_decision: DecisionResult,
        scenario: Scenario,
        include_explanation: bool = True,
        explanation_tier: ExplanationTier = ExplanationTier.INSTITUTIONAL,
    ) -> CounterfactualResponse:
        """Analyze a single what-if scenario."""
        baseline_outcome = self._decision_to_outcome(baseline_decision)
        counterfactual_outcome = self._evaluate_scenario(baseline_decision, scenario)
        delta = self._delta_analyzer.compare(baseline_outcome, counterfactual_outcome)

        explanation = None
        if include_explanation:
            explanation = self._generate_explanation(baseline_outcome, counterfactual_outcome, delta, scenario)

        citations: list[Citation] = []
        if counterfactual_outcome.framework != baseline_outcome.framework:
            citations = self.decoder.citations.get_citations(
                rule_id=baseline_decision.rule_id,
                framework=counterfactual_outcome.framework,
                max_citations=3,
            )

        return CounterfactualResponse(
            baseline_decision_id=baseline_decision.rule_id,
            scenario_applied=scenario,
            baseline_outcome=baseline_outcome,
            counterfactual_outcome=counterfactual_outcome,
            delta=delta,
            explanation=explanation,
            citations=citations,
        )

    def analyze_by_id(self, request: Any) -> CounterfactualResponse:
        """Analyze counterfactual by decision ID."""
        return CounterfactualResponse(
            baseline_decision_id=request.baseline_decision_id,
            scenario_applied=request.scenario,
            baseline_outcome=OutcomeSummary(status="UNKNOWN", framework="Unknown", risk_level="MEDIUM"),
            counterfactual_outcome=OutcomeSummary(status="UNKNOWN", framework="Unknown", risk_level="MEDIUM"),
            delta=DeltaAnalysis(),
            explanation=CounterfactualExplanation(summary="Could not find baseline decision", key_differences=[]),
        )

    def compare(self, baseline_decision: DecisionResult, scenarios: list[Scenario]) -> ComparisonMatrix:
        """Compare multiple scenarios against baseline."""
        baseline_outcome = self._decision_to_outcome(baseline_decision)
        results: list[CounterfactualResponse] = []

        for scenario in scenarios:
            result = self.analyze(baseline_decision, scenario, include_explanation=False)
            results.append(result)

        matrix = self._build_matrix(baseline_outcome, results)
        insights = self._generate_insights(baseline_outcome, results)

        return ComparisonMatrix(
            baseline=baseline_outcome,
            scenarios=scenarios,
            results=results,
            matrix=matrix,
            insights=insights,
        )

    def compare_by_id(self, request: Any) -> ComparisonMatrix:
        """Compare scenarios by baseline decision ID."""
        return ComparisonMatrix(
            baseline=OutcomeSummary(status="UNKNOWN", framework="Unknown"),
            scenarios=request.scenarios,
            results=[],
            matrix={},
            insights=[MatrixInsight(type="warning", text="Could not find baseline decision")],
        )

    def _decision_to_outcome(self, decision: DecisionResult) -> OutcomeSummary:
        """Convert DecisionResult to OutcomeSummary."""
        outcome = (decision.decision or "").lower()
        if outcome in ("authorized", "compliant", "approved", "exempt"):
            status = "APPROVED"
        elif outcome in ("conditional", "requires_review", "pending"):
            status = "CONDITIONAL"
        elif outcome in ("not_authorized", "non_compliant", "denied", "prohibited"):
            status = "DENIED"
        else:
            status = "UNKNOWN"

        framework = "Unknown"
        if decision.rule_metadata and decision.rule_metadata.source:
            doc_id = decision.rule_metadata.source.document_id
            if doc_id:
                framework_map = {"mica": "MiCA", "fca": "FCA", "sec": "SEC", "mas": "MAS", "finma": "FINMA"}
                for key, name in framework_map.items():
                    if key in doc_id.lower():
                        framework = name
                        break

        if status == "DENIED":
            risk_level = "HIGH"
        elif status == "CONDITIONAL":
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        conditions = [o.description or o.id for o in decision.obligations if o.description or o.id]

        return OutcomeSummary(status=status, framework=framework, risk_level=risk_level, conditions=conditions)  # type: ignore[arg-type]

    def _evaluate_scenario(self, baseline_decision: DecisionResult, scenario: Scenario) -> OutcomeSummary:
        """Evaluate a counterfactual scenario."""
        if scenario.type == ScenarioType.JURISDICTION_CHANGE:
            return self._apply_jurisdiction_change(baseline_decision, scenario)
        elif scenario.type == ScenarioType.ENTITY_CHANGE:
            return self._apply_entity_change(baseline_decision, scenario)
        elif scenario.type == ScenarioType.THRESHOLD:
            return self._apply_threshold_change(baseline_decision, scenario)
        elif scenario.type == ScenarioType.TEMPORAL:
            return self._apply_temporal_change(baseline_decision, scenario)
        elif scenario.type == ScenarioType.ACTIVITY_RESTRUCTURE:
            return self._apply_activity_restructure(baseline_decision, scenario)
        elif scenario.type == ScenarioType.PROTOCOL_CHANGE:
            return self._apply_protocol_change(baseline_decision, scenario)
        elif scenario.type == ScenarioType.REGULATORY_CHANGE:
            return self._apply_regulatory_change(baseline_decision, scenario)
        else:
            return self._decision_to_outcome(baseline_decision)

    def _apply_jurisdiction_change(self, baseline_decision: DecisionResult, scenario: Scenario) -> OutcomeSummary:
        """Apply jurisdiction change scenario."""
        params = scenario.parameters
        new_jurisdiction = params.get("to_jurisdiction", "EU")

        jurisdiction_frameworks = {"EU": "MiCA", "UK": "FCA", "US": "SEC", "SG": "MAS", "CH": "FINMA"}
        new_framework = jurisdiction_frameworks.get(new_jurisdiction, "Unknown")

        baseline_outcome = self._decision_to_outcome(baseline_decision)

        if new_framework == baseline_outcome.framework:
            return baseline_outcome

        if new_framework == "MiCA":
            return OutcomeSummary(
                status="CONDITIONAL",
                framework="MiCA",
                risk_level="MEDIUM",
                conditions=["MiCA authorization required", "Whitepaper publication"],
            )
        elif new_framework == "FCA":
            return OutcomeSummary(
                status="CONDITIONAL",
                framework="FCA",
                risk_level="MEDIUM",
                conditions=["FCA registration required", "Promotion restrictions apply"],
            )
        elif new_framework == "SEC":
            return OutcomeSummary(
                status="CONDITIONAL",
                framework="SEC",
                risk_level="HIGH",
                conditions=["Securities registration required", "Accredited investor only"],
            )
        else:
            return OutcomeSummary(
                status="CONDITIONAL",
                framework=new_framework,
                risk_level="MEDIUM",
                conditions=[f"{new_framework} compliance review required"],
            )

    def _apply_entity_change(self, baseline_decision: DecisionResult, scenario: Scenario) -> OutcomeSummary:
        """Apply entity type change scenario."""
        params = scenario.parameters
        new_entity_type = params.get("to_entity_type", "corporate")
        baseline_outcome = self._decision_to_outcome(baseline_decision)

        if new_entity_type == "retail":
            return OutcomeSummary(
                status="CONDITIONAL" if baseline_outcome.status == "APPROVED" else baseline_outcome.status,
                framework=baseline_outcome.framework,
                risk_level="MEDIUM" if baseline_outcome.risk_level == "LOW" else baseline_outcome.risk_level,
                conditions=baseline_outcome.conditions + ["Retail investor protections apply"],
            )
        elif new_entity_type == "institutional":
            return OutcomeSummary(
                status="APPROVED" if baseline_outcome.status == "CONDITIONAL" else baseline_outcome.status,
                framework=baseline_outcome.framework,
                risk_level="LOW" if baseline_outcome.risk_level == "MEDIUM" else baseline_outcome.risk_level,
                conditions=[c for c in baseline_outcome.conditions if "retail" not in c.lower()],
            )
        else:
            return baseline_outcome

    def _apply_threshold_change(self, baseline_decision: DecisionResult, scenario: Scenario) -> OutcomeSummary:
        """Apply threshold change scenario."""
        params = scenario.parameters
        threshold_type = params.get("threshold_type", "amount")
        new_value = params.get("new_value", 0)
        baseline_outcome = self._decision_to_outcome(baseline_decision)

        if threshold_type == "amount" and new_value > 5_000_000:
            return OutcomeSummary(
                status="CONDITIONAL",
                framework=baseline_outcome.framework,
                risk_level="HIGH",
                conditions=baseline_outcome.conditions + ["Large value transaction - enhanced due diligence"],
            )
        elif threshold_type == "holders" and new_value > 150:
            return OutcomeSummary(
                status="CONDITIONAL",
                framework=baseline_outcome.framework,
                risk_level="MEDIUM",
                conditions=baseline_outcome.conditions + ["Public offer threshold exceeded"],
            )
        else:
            return baseline_outcome

    def _apply_temporal_change(self, baseline_decision: DecisionResult, scenario: Scenario) -> OutcomeSummary:
        """Apply temporal change scenario."""
        params = scenario.parameters
        new_date = params.get("effective_date", "2024-07-01")
        baseline_outcome = self._decision_to_outcome(baseline_decision)

        if new_date >= "2024-06-30" and baseline_outcome.framework == "MiCA":
            return OutcomeSummary(
                status=baseline_outcome.status,
                framework="MiCA",
                risk_level=baseline_outcome.risk_level,
                conditions=baseline_outcome.conditions + ["Full MiCA regime now applies"],
            )
        return baseline_outcome

    def _apply_activity_restructure(self, baseline_decision: DecisionResult, scenario: Scenario) -> OutcomeSummary:
        """Apply activity restructure scenario."""
        params = scenario.parameters
        new_activity = params.get("new_activity", "custody")
        baseline_outcome = self._decision_to_outcome(baseline_decision)

        activity_requirements = {
            "custody": ["Safekeeping requirements", "Segregation of assets"],
            "trading": ["Trading venue authorization", "Best execution"],
            "public_offer": ["Whitepaper publication", "Investor disclosures"],
            "swap": ["Derivative regulations", "Margin requirements"],
        }

        new_conditions = activity_requirements.get(new_activity, [])
        return OutcomeSummary(
            status="CONDITIONAL",
            framework=baseline_outcome.framework,
            risk_level="MEDIUM",
            conditions=new_conditions,
        )

    def _apply_protocol_change(self, baseline_decision: DecisionResult, scenario: Scenario) -> OutcomeSummary:
        """Apply protocol/technology change scenario."""
        params = scenario.parameters
        new_protocol = params.get("protocol", "ethereum")
        baseline_outcome = self._decision_to_outcome(baseline_decision)

        if new_protocol in ("bitcoin", "ethereum"):
            return baseline_outcome
        else:
            return OutcomeSummary(
                status="CONDITIONAL",
                framework=baseline_outcome.framework,
                risk_level="MEDIUM",
                conditions=baseline_outcome.conditions + ["Novel protocol - additional review required"],
            )

    def _apply_regulatory_change(self, baseline_decision: DecisionResult, scenario: Scenario) -> OutcomeSummary:
        """Apply regulatory change scenario."""
        params = scenario.parameters
        regulation_change = params.get("change_type", "amendment")
        baseline_outcome = self._decision_to_outcome(baseline_decision)

        if regulation_change == "stricter":
            return OutcomeSummary(
                status="CONDITIONAL" if baseline_outcome.status == "APPROVED" else "DENIED",
                framework=baseline_outcome.framework,
                risk_level="HIGH",
                conditions=baseline_outcome.conditions + ["New regulatory requirements"],
            )
        elif regulation_change == "relaxed":
            return OutcomeSummary(
                status="APPROVED" if baseline_outcome.status == "CONDITIONAL" else baseline_outcome.status,
                framework=baseline_outcome.framework,
                risk_level="LOW",
                conditions=[c for c in baseline_outcome.conditions if "required" not in c.lower()],
            )
        else:
            return baseline_outcome

    def _generate_explanation(
        self, baseline: OutcomeSummary, counterfactual: OutcomeSummary, delta: DeltaAnalysis, scenario: Scenario
    ) -> CounterfactualExplanation:
        """Generate explanation for counterfactual analysis."""
        summary_parts = []

        if delta.status_changed:
            summary_parts.append(f"Status would change from {delta.status_from} to {delta.status_to}.")

        if delta.framework_changed:
            summary_parts.append(
                f"Regulatory framework would change from {baseline.framework} to {counterfactual.framework}."
            )

        if delta.risk_delta != 0:
            direction = "increase" if delta.risk_delta > 0 else "decrease"
            summary_parts.append(f"Risk level would {direction} by {abs(delta.risk_delta)} level(s).")

        if not summary_parts:
            summary_parts.append("No significant changes would result from this scenario.")

        summary = " ".join(summary_parts)

        key_differences: list[dict[str, str]] = []

        for req in delta.new_requirements[:3]:
            key_differences.append({"type": "new_requirement", "description": req})

        for req in delta.removed_requirements[:3]:
            key_differences.append({"type": "removed_requirement", "description": req})

        for factor in delta.risk_factors_added:
            key_differences.append({"type": "risk_increase", "description": factor})

        for factor in delta.risk_factors_removed:
            key_differences.append({"type": "risk_decrease", "description": factor})

        return CounterfactualExplanation(summary=summary, key_differences=key_differences)

    def _build_matrix(self, baseline: OutcomeSummary, results: list[CounterfactualResponse]) -> dict[str, list[str]]:
        """Build comparison matrix data structure."""
        matrix: dict[str, list[str]] = {
            "scenario": ["Baseline"],
            "status": [baseline.status],
            "framework": [baseline.framework],
            "risk_level": [baseline.risk_level],
            "conditions_count": [str(len(baseline.conditions))],
        }

        for i, result in enumerate(results):
            scenario_name = result.scenario_applied.name or f"Scenario {i + 1}"
            matrix["scenario"].append(scenario_name)
            matrix["status"].append(result.counterfactual_outcome.status)
            matrix["framework"].append(result.counterfactual_outcome.framework)
            matrix["risk_level"].append(result.counterfactual_outcome.risk_level)
            matrix["conditions_count"].append(str(len(result.counterfactual_outcome.conditions)))

        return matrix

    def _generate_insights(
        self, baseline: OutcomeSummary, results: list[CounterfactualResponse]
    ) -> list[MatrixInsight]:
        """Generate insights from comparison analysis."""
        insights: list[MatrixInsight] = []

        best_result = None
        best_score = self._outcome_score(baseline)

        for result in results:
            score = self._outcome_score(result.counterfactual_outcome)
            if score > best_score:
                best_score = score
                best_result = result

        if best_result:
            scenario_name = best_result.scenario_applied.name or "Alternative scenario"
            insights.append(
                MatrixInsight(
                    type="recommendation",
                    text=f"{scenario_name} would improve compliance outcome to {best_result.counterfactual_outcome.status}.",
                )
            )

        worst_result = None
        worst_score = self._outcome_score(baseline)

        for result in results:
            score = self._outcome_score(result.counterfactual_outcome)
            if score < worst_score:
                worst_score = score
                worst_result = result

        if worst_result:
            scenario_name = worst_result.scenario_applied.name or "Alternative scenario"
            insights.append(
                MatrixInsight(
                    type="warning",
                    text=f"Avoid {scenario_name} - would result in {worst_result.counterfactual_outcome.status} status.",
                )
            )

        approved_jurisdictions = []
        for result in results:
            if (
                result.scenario_applied.type == ScenarioType.JURISDICTION_CHANGE
                and result.counterfactual_outcome.status == "APPROVED"
            ):
                jurisdiction = result.scenario_applied.parameters.get("to_jurisdiction")
                if jurisdiction:
                    approved_jurisdictions.append(jurisdiction)

        if approved_jurisdictions and baseline.status != "APPROVED":
            insights.append(
                MatrixInsight(
                    type="opportunity",
                    text=f"Consider operating in {', '.join(approved_jurisdictions)} for smoother compliance path.",
                )
            )

        return insights

    def _outcome_score(self, outcome: OutcomeSummary) -> float:
        """Score an outcome for comparison (higher is better)."""
        status_scores = {"APPROVED": 3, "CONDITIONAL": 2, "DENIED": 0, "UNKNOWN": 1}
        risk_scores = {"LOW": 3, "MEDIUM": 2, "HIGH": 1, "CRITICAL": 0}

        status_score = status_scores.get(outcome.status, 1)
        risk_score = risk_scores.get(outcome.risk_level, 2)
        condition_penalty = min(len(outcome.conditions), 5) * 0.2

        return status_score + risk_score - condition_penalty

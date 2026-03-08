"""Tier 2: Semantic Similarity with Embeddings.

Provides embedding-based semantic similarity checking with graceful fallback
to heuristics when ML dependencies (sentence-transformers) are unavailable.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.config import get_sentence_transformer
from src.rules.service import ConsistencyEvidence, Rule

# =============================================================================
# Availability Check
# =============================================================================

_EMBEDDING_AVAILABLE: bool | None = None


def embedding_available() -> bool:
    """Check if sentence-transformers is available."""
    global _EMBEDDING_AVAILABLE
    if _EMBEDDING_AVAILABLE is None:
        try:
            import sentence_transformers  # noqa: F401

            _EMBEDDING_AVAILABLE = True
        except ImportError:
            _EMBEDDING_AVAILABLE = False
    return _EMBEDDING_AVAILABLE


# =============================================================================
# Result Dataclass
# =============================================================================


@dataclass
class SimilarityResult:
    """Result from similarity computation."""

    label: str  # "high", "medium", "low"
    score: float  # 0.0-1.0
    details: str
    matched_segments: list[tuple[str, str, float]] = field(default_factory=list)


# =============================================================================
# EmbeddingChecker
# =============================================================================


class EmbeddingChecker:
    """Dual-mode semantic checker with ML and heuristic fallback.

    When sentence-transformers is available, uses all-MiniLM-L6-v2 model
    for embeddings. Falls back to TF-IDF weighted keyword overlap and
    n-gram matching when ML is unavailable.
    """

    HIGH_THRESHOLD = 0.75
    MEDIUM_THRESHOLD = 0.50

    MODEL_NAME = "all-MiniLM-L6-v2"
    EMBEDDING_DIM = 384

    def __init__(self, use_ml: bool | None = None):
        if use_ml is None:
            self.use_ml = embedding_available()
        else:
            self.use_ml = use_ml and embedding_available()

    @staticmethod
    def _get_model() -> Any:
        return get_sentence_transformer()

    # -------------------------------------------------------------------------
    # Public Check Methods
    # -------------------------------------------------------------------------

    def check_semantic_alignment(
        self,
        rule: Rule,
        source_text: str | None = None,
    ) -> ConsistencyEvidence:
        """Check semantic similarity between rule logic and source."""
        if not source_text:
            return self._make_evidence(
                category="semantic_alignment",
                label="warning",
                score=0.5,
                details="No source text provided for semantic analysis",
            )

        rule_text = self._extract_rule_text(rule)
        if not rule_text:
            return self._make_evidence(
                category="semantic_alignment",
                label="warning",
                score=0.5,
                details="No text extracted from rule for semantic analysis",
            )

        result = self._compute_similarity(rule_text, source_text)

        if result.score >= self.HIGH_THRESHOLD:
            label = "pass"
        elif result.score >= self.MEDIUM_THRESHOLD:
            label = "warning"
        else:
            label = "fail"

        return self._make_evidence(
            category="semantic_alignment",
            label=label,
            score=result.score,
            details=result.details,
            source_span=self._get_best_matching_span(result),
            rule_element="description, decision_tree",
        )

    def check_obligation_similarity(
        self,
        rule: Rule,
        source_text: str | None = None,
    ) -> ConsistencyEvidence:
        """Check rule obligations match source requirements."""
        if not source_text:
            return self._make_evidence(
                category="obligation_similarity",
                label="warning",
                score=0.5,
                details="No source text provided for obligation analysis",
            )

        deontic_sentences = self._extract_deontic_sentences(source_text)
        if not deontic_sentences:
            return self._make_evidence(
                category="obligation_similarity",
                label="pass",
                score=0.9,
                details="No deontic obligations found in source text",
            )

        rule_obligations = self._extract_rule_obligations(rule)
        if not rule_obligations:
            return self._make_evidence(
                category="obligation_similarity",
                label="warning",
                score=0.5,
                details="No obligations found in rule to compare",
            )

        source_combined = " ".join(deontic_sentences)
        rule_combined = " ".join(rule_obligations)
        result = self._compute_similarity(rule_combined, source_combined)

        if result.score >= self.HIGH_THRESHOLD:
            label = "pass"
        elif result.score >= self.MEDIUM_THRESHOLD:
            label = "warning"
        else:
            label = "fail"

        return self._make_evidence(
            category="obligation_similarity",
            label=label,
            score=result.score,
            details=f"Obligation match: {result.details}",
            source_span=deontic_sentences[0] if deontic_sentences else None,
            rule_element="decision_tree.obligations",
        )

    def check_condition_grounding(
        self,
        rule: Rule,
        source_text: str | None = None,
    ) -> ConsistencyEvidence:
        """Check conditions are grounded in source text."""
        if not source_text:
            return self._make_evidence(
                category="condition_grounding",
                label="warning",
                score=0.5,
                details="No source text provided for condition grounding",
            )

        conditions = self._extract_conditions(rule)
        if not conditions:
            return self._make_evidence(
                category="condition_grounding",
                label="pass",
                score=1.0,
                details="No conditions in rule to ground",
            )

        grounded = 0
        ungrounded = []

        for condition_text in conditions:
            result = self._compute_similarity(condition_text, source_text)
            if result.score >= self.MEDIUM_THRESHOLD:
                grounded += 1
            else:
                ungrounded.append(condition_text)

        grounding_ratio = grounded / len(conditions) if conditions else 0

        if grounding_ratio >= 0.8:
            label = "pass"
        elif grounding_ratio >= 0.5:
            label = "warning"
        else:
            label = "fail"

        details = f"Condition grounding: {grounded}/{len(conditions)} conditions grounded"
        if ungrounded:
            details += f". Ungrounded: {', '.join(ungrounded[:3])}"

        return self._make_evidence(
            category="condition_grounding",
            label=label,
            score=grounding_ratio,
            details=details,
            rule_element="applies_if",
        )

    # -------------------------------------------------------------------------
    # Similarity Computation
    # -------------------------------------------------------------------------

    def _compute_similarity(self, text1: str, text2: str) -> SimilarityResult:
        if self.use_ml:
            return self._compute_ml_similarity(text1, text2)
        return self._compute_heuristic_similarity(text1, text2)

    def _compute_ml_similarity(self, text1: str, text2: str) -> SimilarityResult:
        model = self._get_model()
        if model is None:
            return self._compute_heuristic_similarity(text1, text2)

        try:
            embeddings = model.encode([text1, text2], convert_to_numpy=True)
            emb1, emb2 = embeddings[0], embeddings[1]
            score = float(self._cosine_similarity(emb1, emb2))

            if score >= self.HIGH_THRESHOLD:
                label = "high"
            elif score >= self.MEDIUM_THRESHOLD:
                label = "medium"
            else:
                label = "low"

            return SimilarityResult(
                label=label,
                score=score,
                details=f"ML embedding similarity: {score:.3f}",
                matched_segments=[(text1[:100], text2[:100], score)],
            )
        except Exception:
            return self._compute_heuristic_similarity(text1, text2)

    def _compute_heuristic_similarity(self, text1: str, text2: str) -> SimilarityResult:
        tokens1 = self._tokenize(text1)
        tokens2 = self._tokenize(text2)

        if not tokens1 or not tokens2:
            return SimilarityResult(
                label="low",
                score=0.0,
                details="Unable to tokenize texts for comparison",
            )

        tfidf_score = self._tfidf_overlap(tokens1, tokens2)
        ngram_score = self._ngram_similarity(text1, text2)
        jaccard_score = self._jaccard_similarity(tokens1, tokens2)

        score = 0.4 * tfidf_score + 0.35 * ngram_score + 0.25 * jaccard_score

        if score >= self.HIGH_THRESHOLD:
            label = "high"
        elif score >= self.MEDIUM_THRESHOLD:
            label = "medium"
        else:
            label = "low"

        return SimilarityResult(
            label=label,
            score=score,
            details=(
                f"Heuristic similarity: {score:.3f} "
                f"(tfidf={tfidf_score:.2f}, ngram={ngram_score:.2f}, jaccard={jaccard_score:.2f})"
            ),
        )

    # -------------------------------------------------------------------------
    # Heuristic Methods
    # -------------------------------------------------------------------------

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r"\b[a-zA-Z]{2,}\b", text.lower())

    def _tfidf_overlap(self, tokens1: list[str], tokens2: list[str]) -> float:
        all_tokens = set(tokens1) | set(tokens2)
        if not all_tokens:
            return 0.0

        tf1 = {t: tokens1.count(t) for t in set(tokens1)}
        tf2 = {t: tokens2.count(t) for t in set(tokens2)}
        df = {t: (1 if t in tf1 else 0) + (1 if t in tf2 else 0) for t in all_tokens}
        idf = {t: math.log(3 / (df[t] + 1)) + 1 for t in all_tokens}

        vec1 = [tf1.get(t, 0) * idf[t] for t in all_tokens]
        vec2 = [tf2.get(t, 0) * idf[t] for t in all_tokens]
        return self._cosine_similarity(vec1, vec2)

    def _ngram_similarity(self, text1: str, text2: str, n_values: list[int] | None = None) -> float:
        if n_values is None:
            n_values = [2, 3]
        text1_lower = text1.lower()
        text2_lower = text2.lower()

        total_score = 0.0
        for n in n_values:
            ngrams1 = set(text1_lower[i : i + n] for i in range(len(text1_lower) - n + 1))
            ngrams2 = set(text2_lower[i : i + n] for i in range(len(text2_lower) - n + 1))
            if ngrams1 and ngrams2:
                total_score += len(ngrams1 & ngrams2) / len(ngrams1 | ngrams2)

        return total_score / len(n_values) if n_values else 0.0

    def _jaccard_similarity(self, tokens1: list[str], tokens2: list[str]) -> float:
        set1, set2 = set(tokens1), set(tokens2)
        if not set1 and not set2:
            return 0.0
        return len(set1 & set2) / len(set1 | set2)

    @staticmethod
    def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
        dot_product = sum(a * b for a, b in zip(vec1, vec2, strict=False))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot_product / (norm1 * norm2)

    # -------------------------------------------------------------------------
    # Text Extraction
    # -------------------------------------------------------------------------

    def _extract_rule_text(self, rule: Rule) -> str:
        parts = []
        if rule.description:
            parts.append(rule.description)
        parts.extend(self._extract_decision_results(rule))
        if rule.interpretation_notes:
            parts.append(rule.interpretation_notes)
        return " ".join(parts)

    def _extract_decision_results(self, rule: Rule) -> list[str]:
        results: list[str] = []

        def traverse(node: object) -> None:
            if node is None:
                return
            if hasattr(node, "result") and node.result:
                results.append(node.result)
            if hasattr(node, "true_branch"):
                traverse(node.true_branch)
            if hasattr(node, "false_branch"):
                traverse(node.false_branch)

        if rule.decision_tree:
            traverse(rule.decision_tree)
        return results

    def _extract_deontic_sentences(self, text: str) -> list[str]:
        deontic_pattern = re.compile(
            r"(shall|must|may|required|permitted|obliged|prohibited|forbidden)",
            re.IGNORECASE,
        )
        sentences = re.split(r"[.!?]\s+", text)
        return [s.strip() for s in sentences if deontic_pattern.search(s)]

    def _extract_rule_obligations(self, rule: Rule) -> list[str]:
        obligations = list(self._extract_decision_results(rule))
        if rule.description:
            deontic_pattern = re.compile(r"(shall|must|required|obliged)", re.IGNORECASE)
            if deontic_pattern.search(rule.description):
                obligations.append(rule.description)
        return obligations

    def _extract_conditions(self, rule: Rule) -> list[str]:
        conditions: list[str] = []

        def extract_from_spec(cond: object) -> list[str]:
            texts: list[str] = []
            if hasattr(cond, "field") and hasattr(cond, "value"):
                op = getattr(cond, "operator", "==")
                texts.append(f"{cond.field} {op} {cond.value}")
            if hasattr(cond, "all") and cond.all:
                for c in cond.all:
                    texts.extend(extract_from_spec(c))
            if hasattr(cond, "any") and cond.any:
                for c in cond.any:
                    texts.extend(extract_from_spec(c))
            return texts

        if rule.applies_if:
            conditions.extend(extract_from_spec(rule.applies_if))

        def extract_from_tree(node: object) -> None:
            if node is None:
                return
            if hasattr(node, "condition") and node.condition:
                conditions.extend(extract_from_spec(node.condition))
            if hasattr(node, "true_branch"):
                extract_from_tree(node.true_branch)
            if hasattr(node, "false_branch"):
                extract_from_tree(node.false_branch)

        if rule.decision_tree:
            extract_from_tree(rule.decision_tree)
        return conditions

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _make_evidence(
        self,
        category: str,
        label: str,
        score: float,
        details: str,
        source_span: str | None = None,
        rule_element: str | None = None,
    ) -> ConsistencyEvidence:
        return ConsistencyEvidence(
            tier=2,
            category=category,
            label=label,
            score=score,
            details=details,
            source_span=source_span,
            rule_element=rule_element,
            timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )

    def _get_best_matching_span(self, result: SimilarityResult, max_len: int = 100) -> str | None:
        if not result.matched_segments:
            return None
        _, source_seg, _ = result.matched_segments[0]
        return source_seg[:max_len] if source_seg else None


# =============================================================================
# Module-Level Convenience Functions
# =============================================================================

_default_checker: EmbeddingChecker | None = None


def _get_checker() -> EmbeddingChecker:
    global _default_checker
    if _default_checker is None:
        _default_checker = EmbeddingChecker()
    return _default_checker


def check_semantic_alignment(rule: Rule, source_text: str | None = None) -> ConsistencyEvidence:
    """Check semantic similarity between rule logic and source."""
    return _get_checker().check_semantic_alignment(rule, source_text)


def check_obligation_similarity(rule: Rule, source_text: str | None = None) -> ConsistencyEvidence:
    """Check rule obligations match source requirements."""
    return _get_checker().check_obligation_similarity(rule, source_text)


def check_condition_grounding(rule: Rule, source_text: str | None = None) -> ConsistencyEvidence:
    """Check conditions are grounded in source text."""
    return _get_checker().check_condition_grounding(rule, source_text)

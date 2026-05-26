"""T3 NLI gate — DeBERTa entailment check on rationale-as-it-streams.

Runs every 50 tokens. Premise = rule.canonical_statement. Hypothesis = current
text buffer. Early termination on score<0.6, final pass at >=0.7.

DeBERTa loading is lazy and shielded behind the optional `[ml]` extras. When the
model is unavailable, the gate falls back to a deterministic stub scorer based
on simple keyword overlap; tests cover both paths.

See spec §6.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

NLI_CADENCE_TOKENS = 50
NLI_RETRACT_THRESHOLD = 0.6
NLI_VERIFY_THRESHOLD = 0.7


def _approx_token_count(text: str) -> int:
    """Approximate word-piece tokens by counting word boundaries.

    Avoids loading a real tokenizer when only the cadence trigger matters.
    """
    return len(re.findall(r"\S+", text))


def _stub_score(premise: str, hypothesis: str) -> float:
    """Deterministic fallback when DeBERTa isn't available.

    Token overlap ratio over the premise's tokens, biased toward the verified
    threshold for substantial overlap and the retracted threshold when overlap
    is weak. Test-friendly and stable; never goes above 0.95 or below 0.1.
    """
    p_toks = set(re.findall(r"[a-z0-9]+", premise.lower()))
    h_toks = set(re.findall(r"[a-z0-9]+", hypothesis.lower()))
    if not p_toks:
        return 0.5
    overlap = len(p_toks & h_toks) / len(p_toks)
    score = 0.1 + 0.85 * overlap
    return max(0.1, min(0.95, score))


@dataclass
class NLIGate:
    """Stateful gate that scores a streaming hypothesis at fixed token cadences."""

    premise: str
    cadence_tokens: int = NLI_CADENCE_TOKENS
    retract_threshold: float = NLI_RETRACT_THRESHOLD
    verify_threshold: float = NLI_VERIFY_THRESHOLD
    _model: Any = None
    _model_loaded: bool = False
    _last_eval_at_tokens: int = 0

    def _ensure_model(self) -> Any:
        if not self._model_loaded:
            try:
                # NLI service is owned by src.verification.nli; reuse if available.
                from src.verification.nli import get_nli_scorer  # type: ignore[attr-defined]

                self._model = get_nli_scorer()
            except (ImportError, AttributeError):
                self._model = None
            self._model_loaded = True
        return self._model

    def _score(self, hypothesis: str) -> float:
        model = self._ensure_model()
        if model is None:
            return _stub_score(self.premise, hypothesis)
        try:
            return float(model.entailment_score(self.premise, hypothesis))
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("nli_score_error", extra={"error": str(exc)})
            return _stub_score(self.premise, hypothesis)

    def should_check(self, hypothesis_so_far: str) -> bool:
        n = _approx_token_count(hypothesis_so_far)
        if n - self._last_eval_at_tokens >= self.cadence_tokens:
            self._last_eval_at_tokens = n
            return True
        return False

    def check(self, hypothesis_so_far: str) -> float:
        """Score the current buffer. Caller decides what to do with the value."""
        return self._score(hypothesis_so_far)

    def final(self, hypothesis: str) -> float:
        """Final score for an already-complete buffer."""
        return self._score(hypothesis)


__all__ = [
    "NLI_CADENCE_TOKENS",
    "NLI_RETRACT_THRESHOLD",
    "NLI_VERIFY_THRESHOLD",
    "NLIGate",
]

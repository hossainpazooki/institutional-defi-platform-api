"""Evaluate credit decision quality -- confidence calibration, citation accuracy, consistency."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvalResult:
    name: str
    passed: bool
    score: float
    threshold: float
    details: dict[str, Any] = field(default_factory=dict)


class CreditDecisionQualityEval:
    """Evaluate quality of credit synthesis agent output.

    Checks:
    1. Confidence calibration (40%) — confidence aligns with signal strength
    2. Citation accuracy (30%) — all citations reference valid agent outputs
    3. Recommendation consistency (30%) — approve/decline matches signals
    """

    def evaluate(
        self,
        agent_output: dict[str, Any],
        threshold: float = 0.70,
    ) -> EvalResult:
        """Score credit decision on calibration, citations, and consistency."""
        steps = agent_output.get("steps", {})
        confidence = agent_output.get("confidence", 0.0)
        recommendation = agent_output.get("recommendation", "")
        citations = agent_output.get("citations", [])

        # Check 1: Confidence calibration
        signal_scores: list[float] = []
        for agent_key in ("financial_analysis", "legal_analysis", "market_analysis"):
            agent_result = steps.get(agent_key, {})
            if "score" in agent_result:
                signal_scores.append(agent_result["score"])
        if signal_scores:
            avg_signal = sum(signal_scores) / len(signal_scores)
            calibration_score = 1.0 - min(abs(confidence - avg_signal), 1.0)
        else:
            calibration_score = 1.0 if 0.0 <= confidence <= 1.0 else 0.0

        # Check 2: Citation accuracy
        valid_sources = set(steps.keys())
        if citations:
            valid_count = sum(1 for c in citations if c.get("source") in valid_sources)
            citation_score = valid_count / len(citations)
        else:
            citation_score = 1.0

        # Check 3: Recommendation consistency
        if recommendation and signal_scores:
            approve_signals = sum(1 for s in signal_scores if s >= 0.5)
            if (recommendation == "approve" and approve_signals > len(signal_scores) / 2) or (
                recommendation == "decline" and approve_signals <= len(signal_scores) / 2
            ):
                consistency_score = 1.0
            else:
                consistency_score = 0.5
        else:
            consistency_score = 1.0

        score = 0.4 * calibration_score + 0.3 * citation_score + 0.3 * consistency_score

        return EvalResult(
            name="credit_decision_quality",
            passed=score >= threshold,
            score=score,
            threshold=threshold,
            details={
                "calibration_score": calibration_score,
                "citation_score": citation_score,
                "consistency_score": consistency_score,
            },
        )

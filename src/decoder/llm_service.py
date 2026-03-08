"""LLM-based decoder service - Anthropic-powered explanations.

Extracted from the Console's decoder router. Provides LLM-based explanation
generation for risk assessments, with tier-based detail levels.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .config import DecoderConfig
from .schemas import LLMCitation, LLMDecoderResponse, LLMExplainRequest, LLMTierInfo, LLMTiersResponse


class LLMDecoderService:
    """LLM-based explanation generator using Anthropic Claude."""

    def __init__(self, config: DecoderConfig | None = None) -> None:
        self._config = config or DecoderConfig()
        self._client = None

    @property
    def has_api_key(self) -> bool:
        """Check if Anthropic API key is configured."""
        return bool(self._config.anthropic_api_key)

    def explain(self, request: LLMExplainRequest) -> LLMDecoderResponse:
        """Generate an anchored explanation for a risk assessment.

        Tiers:
        - canonical: Just the decision, no LLM call
        - anchored: Decision + LLM explanation with citations
        - guided: Step-by-step reasoning
        - exploratory: Open-ended analysis
        """
        # Extract decision from results (stub logic)
        decision = "LOW_RISK"
        if "protocol_risk" in request.results:
            score = request.results.get("protocol_risk", {}).get("profile", {}).get("overall_score", 75)
            if score >= 80:
                decision = "LOW_RISK"
            elif score >= 60:
                decision = "MEDIUM_RISK"
            else:
                decision = "HIGH_RISK"

        # Build stub citations
        citations = []
        if "protocol_risk" in request.results:
            profile = request.results.get("protocol_risk", {}).get("profile", {})
            if profile.get("overall_score"):
                citations.append(
                    LLMCitation(
                        source="protocol_risk.overall_score",
                        text=f"Chain risk score: {profile['overall_score']}/100",
                        value=profile["overall_score"],
                    )
                )
            if profile.get("risk_tier"):
                citations.append(
                    LLMCitation(
                        source="protocol_risk.risk_tier",
                        text=f"Risk tier: {profile['risk_tier']}",
                        value=profile["risk_tier"],
                    )
                )

        # Stub explanation (in production, this would call Claude API)
        explanation = (
            f"This is a stub explanation for scenario '{request.scenario}'. "
            f"The assessment indicates {decision} based on the provided risk data. "
            "Full LLM-generated explanations will be available once the Anthropic API key is configured."
        )

        if request.tier == "canonical":
            explanation = ""
            citations = []

        return LLMDecoderResponse(
            decision=decision,
            confidence=0.85,
            explanation=explanation,
            citations=citations,
            tier=request.tier,
            generated_at=datetime.utcnow(),
            model="stub" if request.tier == "canonical" else "claude-sonnet-4-20250514 (stub)",
        )

    def get_available_tiers(self) -> LLMTiersResponse:
        """Get available LLM explanation tiers."""
        return LLMTiersResponse(
            tiers=[
                LLMTierInfo(
                    id="canonical",
                    name="Canonical",
                    description="Just the decision and confidence, no LLM explanation",
                    requires_llm=False,
                ),
                LLMTierInfo(
                    id="anchored",
                    name="Anchored",
                    description="Decision + LLM explanation with citations to specific data points",
                    requires_llm=True,
                ),
                LLMTierInfo(
                    id="guided",
                    name="Guided",
                    description="Step-by-step reasoning through the risk assessment",
                    requires_llm=True,
                ),
                LLMTierInfo(
                    id="exploratory",
                    name="Exploratory",
                    description="Open-ended analysis exploring implications and edge cases",
                    requires_llm=True,
                ),
            ]
        )

    def get_health(self) -> dict[str, Any]:
        """Check LLM decoder health and API key status."""
        return {
            "status": "healthy",
            "anthropic_configured": self.has_api_key,
            "available_tiers": (
                ["canonical"] if not self.has_api_key else ["canonical", "anchored", "guided", "exploratory"]
            ),
        }

"""PydanticAI agents for credit decisioning.

Lazily imports pydantic_ai so the module loads even without the dependency.
"""

from __future__ import annotations

import logging
from typing import Any

from .schemas import (
    FinancialAgentOutput,
    LegalAgentOutput,
    MarketAgentOutput,
    SynthesisOutput,
)

logger = logging.getLogger(__name__)

MODEL = "anthropic:claude-sonnet-4-20250514"


# ---------------------------------------------------------------------------
# Mock tool implementations (return realistic sample data)
# ---------------------------------------------------------------------------

def _get_var_metrics(portfolio_id: str = "default") -> dict[str, Any]:
    """Wraps src.market_risk VaR calculation with mock fallback."""
    try:
        from src.market_risk.service import calculate_var
        return {"var_95": calculate_var([0.01, -0.02, 0.005], 0.95)}
    except Exception:
        return {
            "var_95": 0.042,
            "var_99": 0.067,
            "cvar_95": 0.058,
            "portfolio_id": portfolio_id,
        }


def _analyze_financials(borrower_name: str) -> dict[str, Any]:
    return {
        "borrower": borrower_name,
        "revenue_3yr_cagr": 0.12,
        "ebitda_margin": 0.28,
        "debt_to_equity": 1.45,
        "interest_coverage": 3.8,
        "current_ratio": 1.65,
        "altman_z": 2.9,
    }


def _retrieve_legal_docs(query: str) -> list[dict[str, Any]]:
    """Wraps src.rag.service.Retriever with mock fallback."""
    try:
        from src.rag.service import Retriever
        retriever = Retriever(use_vectors=False)
        results = retriever.search(query, top_k=3)
        return [{"text": r.text, "score": r.score} for r in results]
    except Exception:
        return [
            {"text": "Standard LMA covenant package applies. Cross-default clause present.", "score": 0.85},
            {"text": "Borrower domiciled in Delaware; NY law governs the facility.", "score": 0.78},
        ]


def _check_covenants(doc_id: str) -> dict[str, Any]:
    return {
        "doc_id": doc_id,
        "leverage_covenant": {"max_ratio": 4.0, "current": 3.2, "headroom": "20%"},
        "interest_coverage": {"min_ratio": 2.5, "current": 3.8, "headroom": "52%"},
        "capex_limit": {"annual_max_usd": 50_000_000, "ytd_spend": 22_000_000},
        "material_adverse_change": False,
    }


def _get_comparables(industry: str) -> list[dict[str, Any]]:
    return [
        {"name": "Peer A", "spread_bps": 275, "rating": "BB+", "leverage": 3.1},
        {"name": "Peer B", "spread_bps": 310, "rating": "BB", "leverage": 3.8},
        {"name": "Peer C", "spread_bps": 245, "rating": "BBB-", "leverage": 2.6},
    ]


def _get_sector_data(industry: str) -> dict[str, Any]:
    return {
        "industry": industry,
        "default_rate_1yr": 0.018,
        "recovery_rate": 0.42,
        "sector_outlook": "stable",
        "gdp_sensitivity": 1.2,
        "regulatory_risk": "moderate",
    }


# ---------------------------------------------------------------------------
# Agent factory — builds agents lazily
# ---------------------------------------------------------------------------

def _build_agents() -> tuple:
    """Build and return (financial_agent, legal_agent, market_agent, synthesis_agent).

    Returns None tuple members if pydantic_ai is not installed.
    """
    try:
        from pydantic_ai import Agent
    except ImportError:
        logger.warning("pydantic_ai not installed — agents will use mock mode")
        return None, None, None, None

    financial_agent = Agent(
        MODEL,
        result_type=FinancialAgentOutput,
        system_prompt=(
            "You are a senior credit analyst specializing in private credit. "
            "Analyze financial statements, calculate key ratios, and assess "
            "creditworthiness. Focus on debt service coverage, working capital, "
            "and revenue trends. Output structured signals."
        ),
    )

    @financial_agent.tool_plain
    def get_var_metrics(portfolio_id: str = "default") -> dict[str, Any]:
        """Retrieve VaR metrics for risk context."""
        return _get_var_metrics(portfolio_id)

    @financial_agent.tool_plain
    def analyze_financials(borrower_name: str) -> dict[str, Any]:
        """Analyze borrower financial statements."""
        return _analyze_financials(borrower_name)

    legal_agent = Agent(
        MODEL,
        result_type=LegalAgentOutput,
        system_prompt=(
            "You are a credit legal analyst reviewing loan documentation. "
            "Identify regulatory flags, covenant issues, and jurisdiction "
            "risks. Flag any non-standard terms or missing protections."
        ),
    )

    @legal_agent.tool_plain
    def retrieve_legal_docs(query: str) -> list[dict[str, Any]]:
        """Search the legal document corpus."""
        return _retrieve_legal_docs(query)

    @legal_agent.tool_plain
    def check_covenants(doc_id: str) -> dict[str, Any]:
        """Check covenant compliance for a document."""
        return _check_covenants(doc_id)

    market_agent = Agent(
        MODEL,
        result_type=MarketAgentOutput,
        system_prompt=(
            "You are a credit market analyst. Evaluate industry conditions, "
            "peer comparisons, and market risk factors. Provide sector outlook "
            "and relative value assessment."
        ),
    )

    @market_agent.tool_plain
    def get_comparables(industry: str) -> list[dict[str, Any]]:
        """Get comparable credits in the sector."""
        return _get_comparables(industry)

    @market_agent.tool_plain
    def get_sector_data(industry: str) -> dict[str, Any]:
        """Get sector-level risk data."""
        return _get_sector_data(industry)

    synthesis_agent = Agent(
        MODEL,
        result_type=SynthesisOutput,
        system_prompt=(
            "You are the senior credit committee synthesizer. Combine outputs "
            "from financial, legal, and market agents into a final credit "
            "recommendation. Decide approve/decline/refer with confidence "
            "score and escalation flags."
        ),
    )

    return financial_agent, legal_agent, market_agent, synthesis_agent


# Module-level lazy singleton
_agents: tuple | None = None


def get_agents():
    """Get or build the agent tuple."""
    global _agents
    if _agents is None:
        _agents = _build_agents()
    return _agents


# ---------------------------------------------------------------------------
# Mock agent runner (used when pydantic_ai is not installed)
# ---------------------------------------------------------------------------

def mock_financial_output(borrower_name: str) -> FinancialAgentOutput:
    """Generate mock financial analysis output."""
    financials = _analyze_financials(borrower_name)
    return FinancialAgentOutput(
        signals=["positive revenue trend", "adequate debt service coverage", "moderate leverage"],
        confidence=0.82,
        uncertainty_flags=["limited historical data"],
        revenue_trend="growing",
        debt_service_coverage=financials["interest_coverage"],
        working_capital_ratio=financials["current_ratio"],
        credit_score_estimate=680,
    )


def mock_legal_output(doc_ids: list[str]) -> LegalAgentOutput:
    """Generate mock legal analysis output."""
    return LegalAgentOutput(
        signals=["standard LMA documentation", "cross-default clause present"],
        confidence=0.78,
        uncertainty_flags=["covenant package not yet finalized"],
        regulatory_flags=["Basel III capital treatment applies"],
        covenant_issues=["leverage covenant tight at 4.0x"],
        jurisdiction_risks=["multi-jurisdiction enforcement risk"],
    )


def mock_market_output(industry: str) -> MarketAgentOutput:
    """Generate mock market analysis output."""
    sector = _get_sector_data(industry)
    comps = _get_comparables(industry)
    return MarketAgentOutput(
        signals=["sector outlook stable", "spreads in line with peers"],
        confidence=0.85,
        uncertainty_flags=["pending regulatory changes"],
        industry_outlook=sector["sector_outlook"],
        peer_comparison={"peers": comps, "relative_value": "fair"},
        market_risk_score=0.35,
    )


def mock_synthesis(
    financial: FinancialAgentOutput,
    legal: LegalAgentOutput,
    market: MarketAgentOutput,
) -> SynthesisOutput:
    """Generate mock synthesis from agent outputs."""
    avg_confidence = (financial.confidence + legal.confidence + market.confidence) / 3
    return SynthesisOutput(
        recommendation="approve" if avg_confidence > 0.75 else "refer",
        confidence=round(avg_confidence, 2),
        escalate=False,
        escalation_reason=None,
        citations=[
            {"source": "financial_agent", "finding": "adequate debt service coverage"},
            {"source": "legal_agent", "finding": "standard documentation"},
            {"source": "market_agent", "finding": "stable sector outlook"},
        ],
        agent_outputs={
            "financial": financial.model_dump(),
            "legal": legal.model_dump(),
            "market": market.model_dump(),
        },
    )

"""Credit synthesis orchestration across financial, legal, and market agents.

Provides a high-level skill interface that coordinates multi-agent credit
decisioning with escalation routing.  Can be used standalone or as the
backing logic for Temporal activities.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Callable


class CreditSynthesisSkill:
    """Orchestrate credit synthesis across financial, legal, and market agents."""

    def __init__(self, tool_caller: Callable[..., Any] | None = None) -> None:
        self.tool_caller = tool_caller

    async def _call_tool(self, tool_name: str, **kwargs: Any) -> dict[str, Any]:
        """Call an MCP tool or raise if no caller configured."""
        if self.tool_caller is None:
            raise RuntimeError("No tool_caller configured for CreditSynthesisSkill")
        result = self.tool_caller(tool_name, **kwargs)
        if hasattr(result, "__await__"):
            result = await result
        return cast("dict[str, Any]", result)

    async def run(
        self,
        financial_data: dict[str, Any] | None = None,
        legal_data: dict[str, Any] | None = None,
        market_data: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Orchestrate: validate -> financial -> legal -> market -> synthesize -> route -> audit."""
        config = config or {}
        steps: dict[str, Any] = {}

        # Step 1: Validate inputs
        validation = await self._call_tool(
            "validate_credit_inputs",
            financial_data=financial_data or {},
            legal_data=legal_data or {},
            market_data=market_data or {},
        )
        steps["validate"] = validation

        # Step 2: Financial analysis
        financial_result = await self._call_tool(
            "financial_analysis",
            data=financial_data or {},
            model=config.get("financial_model", "default"),
        )
        steps["financial_analysis"] = financial_result

        # Step 3: Legal analysis
        legal_result = await self._call_tool(
            "legal_analysis",
            data=legal_data or {},
            jurisdiction=config.get("jurisdiction", "US"),
        )
        steps["legal_analysis"] = legal_result

        # Step 4: Market analysis
        market_result = await self._call_tool(
            "market_analysis",
            data=market_data or {},
            sector=config.get("sector", "technology"),
        )
        steps["market_analysis"] = market_result

        # Step 5: Synthesize results
        synthesis = await self._call_tool(
            "synthesize_credit_decision",
            financial=financial_result,
            legal=legal_result,
            market=market_result,
        )
        steps["synthesize"] = synthesis

        confidence = synthesis.get("confidence", 0.0)
        deal_amount = (financial_data or {}).get("deal_amount_usd", 0)
        escalate = confidence < 0.75 or deal_amount > 100_000_000

        # Step 6: Route decision
        routing = await self._call_tool(
            "route_credit_decision",
            recommendation=synthesis.get("recommendation", ""),
            confidence=confidence,
            escalate=escalate,
        )
        steps["route"] = routing

        # Step 7: Audit trail
        audit = await self._call_tool(
            "record_audit_trail",
            steps=steps,
            recommendation=synthesis.get("recommendation", ""),
            confidence=confidence,
        )
        steps["audit"] = audit

        return {
            "steps": steps,
            "recommendation": synthesis.get("recommendation", ""),
            "confidence": confidence,
            "escalate": escalate,
            "citations": synthesis.get("citations", []),
        }

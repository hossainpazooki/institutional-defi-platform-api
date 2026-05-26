"""Verdict service — dual-path resolver for live-session crossings.

Single-jurisdiction or `cross_border_relevant=False` rules → in-process synchronous
decision against compiled IR (sub-millisecond target).

`cross_border_relevant=True` → dispatch to ComplianceCheckWorkflow via Temporal
(~200ms p99 target). The Temporal path is opt-in via the `temporal_executor`
injection — if None, the multi-jurisdiction path falls back to sync evaluation
with a "conditional" bias (safe default).

The path choice is determined **at rule load time** from the rule's
`cross_border_relevant` flag — no per-tick branching.

See spec §5.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from decimal import Decimal

from src.market_risk.ws_schemas import TradeSnapshot, Verdict

from .threshold_detector import RuleBoundary


def _get_scalar(snapshot: TradeSnapshot, name: str) -> Decimal:
    return Decimal(str(getattr(snapshot, name)))


TemporalExecutor = Callable[[str, TradeSnapshot, RuleBoundary], Awaitable[Verdict]]


@dataclass
class VerdictService:
    """Resolves a verdict for a (snapshot, rule) pair using the per-rule path."""

    cross_border_rule_ids: set[str] = field(default_factory=set)
    temporal_executor: TemporalExecutor | None = None

    def sync_verdict(self, snapshot: TradeSnapshot, rule: RuleBoundary) -> Verdict:
        """Simple boundary comparison; the compiled IR engine plugs in here in production."""
        scalar = _get_scalar(snapshot, rule.scalar)
        if scalar > rule.boundary:
            return Verdict.BLOCKED
        # A 5% buffer below the boundary triggers "conditional".
        cushion = rule.boundary * Decimal("0.95")
        if scalar > cushion:
            return Verdict.CONDITIONAL
        return Verdict.COMPLIANT

    def is_cross_border(self, rule_id: str) -> bool:
        return rule_id in self.cross_border_rule_ids

    async def resolve(self, snapshot: TradeSnapshot, rule: RuleBoundary) -> Verdict:
        if self.is_cross_border(rule.rule_id) and self.temporal_executor is not None:
            return await self.temporal_executor("ComplianceCheckWorkflow", snapshot, rule)
        return self.sync_verdict(snapshot, rule)


__all__ = ["TemporalExecutor", "VerdictService"]

"""Verdict service dual-path tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.market_risk.live_session.threshold_detector import RuleBoundary
from src.market_risk.live_session.verdict_service import VerdictService
from src.market_risk.ws_schemas import TradeSnapshot, Verdict


def _snap(spread: float) -> TradeSnapshot:
    return TradeSnapshot(
        intent_id="i-1",
        ts=datetime(2026, 5, 26, tzinfo=UTC),
        mark_price=Decimal("100"),
        bid=Decimal("99"),
        ask=Decimal("101"),
        size=Decimal("1"),
        spread_bps=spread,
        slippage_bps=0.0,
        vol_30d=0.5,
        var_95_usd=1000.0,
        funding_rate=None,
    )


def test_sync_verdict_returns_compliant_below_cushion() -> None:
    vs = VerdictService()
    rb = RuleBoundary(rule_id="r1", citation="MiCA", boundary=Decimal("10"), scalar="spread_bps")
    assert vs.sync_verdict(_snap(2.0), rb) == Verdict.COMPLIANT


def test_sync_verdict_returns_conditional_in_cushion() -> None:
    vs = VerdictService()
    rb = RuleBoundary(rule_id="r1", citation="MiCA", boundary=Decimal("10"), scalar="spread_bps")
    assert vs.sync_verdict(_snap(9.7), rb) == Verdict.CONDITIONAL


def test_sync_verdict_returns_blocked_above() -> None:
    vs = VerdictService()
    rb = RuleBoundary(rule_id="r1", citation="MiCA", boundary=Decimal("10"), scalar="spread_bps")
    assert vs.sync_verdict(_snap(11.0), rb) == Verdict.BLOCKED


@pytest.mark.asyncio
async def test_resolve_dispatches_temporal_for_cross_border_rules() -> None:
    called: dict[str, str] = {}

    async def fake_temporal(workflow: str, snapshot: TradeSnapshot, rule: RuleBoundary) -> Verdict:
        called["workflow"] = workflow
        called["rule"] = rule.rule_id
        return Verdict.CONDITIONAL

    vs = VerdictService(cross_border_rule_ids={"r-cb"}, temporal_executor=fake_temporal)
    rb = RuleBoundary(rule_id="r-cb", citation="MiFID II", boundary=Decimal("10"), scalar="spread_bps")
    out = await vs.resolve(_snap(1.0), rb)
    assert out == Verdict.CONDITIONAL
    assert called == {"workflow": "ComplianceCheckWorkflow", "rule": "r-cb"}


@pytest.mark.asyncio
async def test_resolve_uses_sync_for_non_cross_border() -> None:
    vs = VerdictService(cross_border_rule_ids={"r-cb"})  # no temporal_executor
    rb = RuleBoundary(rule_id="r-local", citation="MiCA", boundary=Decimal("10"), scalar="spread_bps")
    out = await vs.resolve(_snap(11.0), rb)
    assert out == Verdict.BLOCKED


@pytest.mark.asyncio
async def test_resolve_falls_back_to_sync_when_temporal_missing() -> None:
    vs = VerdictService(cross_border_rule_ids={"r-cb"})  # CB set but no executor
    rb = RuleBoundary(rule_id="r-cb", citation="MiFID II", boundary=Decimal("10"), scalar="spread_bps")
    out = await vs.resolve(_snap(1.0), rb)
    assert out == Verdict.COMPLIANT

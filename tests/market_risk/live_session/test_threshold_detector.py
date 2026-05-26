"""Threshold detector — verdict transitions emit, same-state ticks don't."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from src.market_risk.live_session.threshold_detector import RuleBoundary, ThresholdDetector
from src.market_risk.ws_schemas import TradeSnapshot, Verdict


def _snap(spread: float, var: float = 1000.0) -> TradeSnapshot:
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
        var_95_usd=var,
        funding_rate=None,
    )


def _verdict_predicate(snapshot: TradeSnapshot, rule: RuleBoundary) -> Verdict:
    scalar = Decimal(str(getattr(snapshot, rule.scalar)))
    if scalar > rule.boundary:
        return Verdict.BLOCKED
    cushion = rule.boundary * Decimal("0.95")
    if scalar > cushion:
        return Verdict.CONDITIONAL
    return Verdict.COMPLIANT


def test_first_tick_does_not_emit() -> None:
    rb = RuleBoundary(rule_id="r1", citation="MiCA", boundary=Decimal("10"), scalar="spread_bps")
    det = ThresholdDetector(boundaries=[rb], verdict_for=_verdict_predicate)
    out = det.detect(_snap(2.0), notional_usd=100_000, position_pct=0.01)
    assert out == []


def test_emit_on_transition() -> None:
    rb = RuleBoundary(rule_id="r1", citation="MiCA", boundary=Decimal("10"), scalar="spread_bps")
    det = ThresholdDetector(boundaries=[rb], verdict_for=_verdict_predicate)
    det.detect(_snap(2.0), notional_usd=100_000, position_pct=0.01)  # baseline
    out = det.detect(_snap(20.0), notional_usd=200_000, position_pct=0.02)  # change zone + cross
    assert len(out) == 1
    crossing = out[0]
    assert crossing.prior_verdict == Verdict.COMPLIANT
    assert crossing.new_verdict == Verdict.BLOCKED


def test_no_emit_on_same_zone() -> None:
    rb = RuleBoundary(rule_id="r1", citation="MiCA", boundary=Decimal("10"), scalar="spread_bps")
    det = ThresholdDetector(boundaries=[rb], verdict_for=_verdict_predicate)
    det.detect(_snap(2.0), notional_usd=100_000, position_pct=0.01)
    # Same scalars → same zone → fast-path returns no crossings.
    out = det.detect(_snap(2.0), notional_usd=100_000, position_pct=0.01)
    assert out == []


def test_emit_includes_direction_up_when_above_boundary() -> None:
    rb = RuleBoundary(rule_id="r1", citation="MiCA", boundary=Decimal("10"), scalar="spread_bps")
    det = ThresholdDetector(boundaries=[rb], verdict_for=_verdict_predicate)
    det.detect(_snap(2.0), notional_usd=100_000, position_pct=0.01)
    out = det.detect(_snap(20.0), notional_usd=200_000, position_pct=0.02)
    assert out[0].direction.value == "crossed_up"

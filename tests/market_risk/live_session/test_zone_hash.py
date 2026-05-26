"""Zone hash determinism + bucketization."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from src.market_risk.live_session.zone_hash import BucketWidths, bucket_for
from src.market_risk.ws_schemas import TradeSnapshot


def _snap(vol_30d: float, spread_bps: float) -> TradeSnapshot:
    return TradeSnapshot(
        intent_id="i-1",
        ts=datetime(2026, 5, 26, tzinfo=UTC),
        mark_price=Decimal("100"),
        bid=Decimal("99"),
        ask=Decimal("101"),
        size=Decimal("1"),
        spread_bps=spread_bps,
        slippage_bps=0.0,
        vol_30d=vol_30d,
        var_95_usd=100.0,
        funding_rate=None,
    )


def test_deterministic_same_inputs_same_hash() -> None:
    s = _snap(0.5, 10.0)
    h1 = bucket_for(s, notional_usd=100_000, position_pct=0.02)
    h2 = bucket_for(s, notional_usd=100_000, position_pct=0.02)
    assert h1 == h2


def test_distinct_when_vol_in_different_bucket() -> None:
    s1 = _snap(0.10, 10.0)  # ~bucket 2
    s2 = _snap(0.20, 10.0)  # ~bucket 4
    h1 = bucket_for(s1, notional_usd=100_000, position_pct=0.02)
    h2 = bucket_for(s2, notional_usd=100_000, position_pct=0.02)
    assert h1 != h2


def test_custom_widths_override_default() -> None:
    s = _snap(0.5, 10.0)
    h_default = bucket_for(s, notional_usd=100_000, position_pct=0.02)
    h_wider = bucket_for(
        s,
        notional_usd=100_000,
        position_pct=0.02,
        widths=BucketWidths(vol_30d=1.0, spread_bps=100.0),
    )
    assert h_default != h_wider


def test_handles_zero_and_inf_safely() -> None:
    s = _snap(0.0, 0.0)
    h = bucket_for(s, notional_usd=0, position_pct=0)
    assert h == (0, 0, 0, 0)

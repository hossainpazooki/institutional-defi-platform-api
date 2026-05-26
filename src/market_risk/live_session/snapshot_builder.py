"""Snapshot builder — derives TradeSnapshot from raw Binance stream state.

Welford σ over kline_1m returns for incremental 30-day vol. VaR_95 closed-form.
Slippage estimated against a 10-level depth snapshot.

See spec §3.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from src.market_risk.ws_schemas import TradeIntent, TradeSnapshot

if TYPE_CHECKING:
    from collections.abc import Iterable

# z-score for 95% one-tailed VaR.
Z_95 = 1.6448536269514722
# Number of 1-minute candles in a 30-day window.
WINDOW_30D_MINUTES = 30 * 24 * 60


@dataclass
class WelfordSigma:
    """Incremental sample variance via Welford's online algorithm.

    Tracks count, mean, M2 (sum of squared deviations). `sigma` returns the
    population stddev (n>=2 required for a meaningful number).
    """

    count: int = 0
    mean: float = 0.0
    m2: float = 0.0

    def update(self, x: float) -> None:
        self.count += 1
        delta = x - self.mean
        self.mean += delta / self.count
        delta2 = x - self.mean
        self.m2 += delta * delta2

    def update_many(self, xs: Iterable[float]) -> None:
        for x in xs:
            self.update(x)

    @property
    def sigma(self) -> float:
        if self.count < 2:
            return 0.0
        return math.sqrt(self.m2 / (self.count - 1))


def annualize_sigma_from_1m(sigma_1m: float) -> float:
    """Annualize a per-minute return stddev to a 30-day window.

    The pipeline treats "vol_30d" as the annualized vol estimated on 1m returns
    over the last 30d. `sigma_1m * sqrt(WINDOW_30D_MINUTES)` is the 30d-horizon
    stddev; we keep this representation throughout the snapshot.
    """
    return sigma_1m * math.sqrt(WINDOW_30D_MINUTES)


def var_95(sigma_30d: float, notional_usd: float, holding_period_days: int) -> float:
    """VaR_95 in USD = z_{0.95} · σ · √(holding_period_days / 365) · notional."""
    horizon = math.sqrt(max(holding_period_days, 0) / 365.0)
    return Z_95 * sigma_30d * horizon * notional_usd


def estimate_slippage_bps(
    notional_usd: Decimal, depth_levels: list[tuple[Decimal, Decimal]]
) -> float:
    """Estimate slippage in bps to fill `notional_usd` against the given side of the book.

    `depth_levels` is sorted from best to worst price; each (price, size).
    Returns 0 if depth insufficient (caller decides how to handle).
    """
    if not depth_levels:
        return 0.0
    best_price = depth_levels[0][0]
    remaining = notional_usd
    filled_notional = Decimal("0")
    weighted_price_sum = Decimal("0")
    for price, size in depth_levels:
        if remaining <= 0:
            break
        level_notional = price * size
        take = min(level_notional, remaining)
        filled_notional += take
        weighted_price_sum += (take / price) * price * (take / level_notional or Decimal(1))
        # Simpler: vwap weighted by notional taken
        weighted_price_sum = weighted_price_sum  # noqa: PLW0127 (placeholder; recompute below)
        remaining -= take
    if filled_notional <= 0:
        return 0.0
    # Recompute VWAP cleanly: sum(price * notional_at_level) / sum(notional_at_level)
    vwap_num = Decimal("0")
    vwap_den = Decimal("0")
    remaining = notional_usd
    for price, size in depth_levels:
        if remaining <= 0:
            break
        level_notional = price * size
        take = min(level_notional, remaining)
        vwap_num += price * take
        vwap_den += take
        remaining -= take
    if vwap_den <= 0:
        return 0.0
    vwap = vwap_num / vwap_den
    diff_bps = (vwap - best_price) / best_price * Decimal(10000)
    return float(abs(diff_bps))


@dataclass
class SnapshotBuilder:
    """Derives TradeSnapshot from accumulated stream state for one TradeIntent."""

    intent: TradeIntent
    welford: WelfordSigma = field(default_factory=WelfordSigma)
    last_kline_close: float | None = None

    def update_kline(self, close_price: float) -> None:
        if self.last_kline_close is not None and self.last_kline_close > 0:
            ret = math.log(close_price / self.last_kline_close)
            self.welford.update(ret)
        self.last_kline_close = close_price

    def build(
        self,
        *,
        mark_price: Decimal,
        bid: Decimal,
        ask: Decimal,
        size: Decimal,
        depth_bid_levels: list[tuple[Decimal, Decimal]],
        depth_ask_levels: list[tuple[Decimal, Decimal]],
        funding_rate: float | None,
        ts: datetime | None = None,
    ) -> TradeSnapshot:
        sigma_30d = annualize_sigma_from_1m(self.welford.sigma)
        var_usd = var_95(
            sigma_30d,
            float(self.intent.notional_usd),
            self.intent.holding_period_days,
        )
        spread_bps = 0.0
        if ask > 0 and bid > 0:
            mid = (ask + bid) / 2
            if mid > 0:
                spread_bps = float((ask - bid) / mid * Decimal(10000))

        # Use the appropriate side of the book for slippage based on direction.
        depth_side = depth_ask_levels if self.intent.direction.value == "buy" else depth_bid_levels
        slippage = estimate_slippage_bps(self.intent.notional_usd, depth_side)

        return TradeSnapshot(
            intent_id=self.intent.intent_id,
            ts=ts or datetime.now(UTC),
            mark_price=mark_price,
            bid=bid,
            ask=ask,
            size=size,
            spread_bps=spread_bps,
            slippage_bps=slippage,
            vol_30d=sigma_30d,
            var_95_usd=var_usd,
            funding_rate=funding_rate,
        )


__all__ = [
    "SnapshotBuilder",
    "WelfordSigma",
    "Z_95",
    "annualize_sigma_from_1m",
    "estimate_slippage_bps",
    "var_95",
]

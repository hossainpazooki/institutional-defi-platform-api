"""Welford σ + VaR + slippage math tests."""

from __future__ import annotations

import math
from decimal import Decimal

from src.market_risk.live_session.snapshot_builder import (
    Z_95,
    WelfordSigma,
    annualize_sigma_from_1m,
    estimate_slippage_bps,
    var_95,
)


def test_welford_matches_numpy_population_var() -> None:
    xs = [0.001, -0.002, 0.0015, 0.0007, -0.001, 0.002, 0.0003, -0.0005, 0.001, 0.0008]
    w = WelfordSigma()
    w.update_many(xs)
    # Reference: sample stddev
    mean = sum(xs) / len(xs)
    var = sum((x - mean) ** 2 for x in xs) / (len(xs) - 1)
    expected = math.sqrt(var)
    assert abs(w.sigma - expected) < 1e-12


def test_welford_zero_for_single_point() -> None:
    w = WelfordSigma()
    w.update(0.001)
    assert w.sigma == 0.0


def test_annualize_sigma_positive() -> None:
    assert annualize_sigma_from_1m(0.001) > 0.001


def test_var_95_closed_form() -> None:
    sigma_30d = 0.5
    notional = 1_000_000.0
    holding_period_days = 10
    expected = Z_95 * sigma_30d * math.sqrt(holding_period_days / 365.0) * notional
    assert abs(var_95(sigma_30d, notional, holding_period_days) - expected) < 1e-6


def test_var_95_zero_holding_period() -> None:
    assert var_95(0.5, 1_000_000.0, 0) == 0.0


def test_slippage_bps_zero_when_no_depth() -> None:
    assert estimate_slippage_bps(Decimal("10000"), []) == 0.0


def test_slippage_bps_increases_with_thin_book() -> None:
    notional = Decimal("100000")
    # Deep book: first level holds the whole order.
    deep = [(Decimal("100"), Decimal("10000"))]
    # Thin book: takes liquidity across multiple worse levels.
    thin = [
        (Decimal("100"), Decimal("100")),
        (Decimal("105"), Decimal("100")),
        (Decimal("110"), Decimal("100")),
        (Decimal("120"), Decimal("100")),
    ]
    s_deep = estimate_slippage_bps(notional, deep)
    s_thin = estimate_slippage_bps(notional, thin)
    assert s_thin > s_deep


def test_welford_deterministic_to_6dp() -> None:
    xs = [(-1) ** i * (i + 1) * 1e-4 for i in range(1000)]
    w1 = WelfordSigma()
    w2 = WelfordSigma()
    w1.update_many(xs)
    w2.update_many(xs)
    assert round(w1.sigma, 6) == round(w2.sigma, 6)

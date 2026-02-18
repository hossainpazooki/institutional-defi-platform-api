"""Market risk service — VaR, CVaR, volatility, liquidity, stress tests, correlations.

Implements Value at Risk (VaR), Conditional VaR (Expected Shortfall),
volatility analysis, and liquidity metrics for crypto portfolios.
Merges Workbench parametric calculations with Console portfolio-level stubs.

References:
- Basel III market risk framework
- FRTB standardized approach for crypto assets
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

from .constants import CVAR_MULTIPLIERS, Z_SCORES
from .schemas import (
    CorrelationPair,
    CorrelationResponse,
    CryptoVolatilityMetrics,
    LiquidityMetrics,
    MarketRiskReport,
    RiskRating,
    StressScenario,
    StressTestResponse,
    VaRResponse,
    VaRResult,
)

# =============================================================================
# VaR / CVaR Calculations (from Workbench)
# =============================================================================


def calculate_var(
    volatility: float,
    confidence_level: float = 0.95,
    holding_period_days: int = 1,
) -> float:
    """Calculate parametric Value at Risk.

    Uses the variance-covariance method assuming normal returns.

    Args:
        volatility: Annualized volatility (e.g., 0.80 for 80%).
        confidence_level: Confidence level (0.90, 0.95, 0.99).
        holding_period_days: Holding period in days.

    Returns:
        VaR as percentage of position value.
    """
    z_score = Z_SCORES.get(confidence_level, 1.645)
    daily_vol = volatility / math.sqrt(365)
    period_vol = daily_vol * math.sqrt(holding_period_days)
    return z_score * period_vol


def calculate_cvar(
    volatility: float,
    confidence_level: float = 0.95,
    holding_period_days: int = 1,
) -> float:
    """Calculate Conditional Value at Risk (Expected Shortfall).

    CVaR represents the expected loss given that VaR is exceeded.

    Args:
        volatility: Annualized volatility.
        confidence_level: Confidence level.
        holding_period_days: Holding period in days.

    Returns:
        CVaR as percentage of position value.
    """
    multiplier = CVAR_MULTIPLIERS.get(confidence_level, 2.063)
    daily_vol = volatility / math.sqrt(365)
    period_vol = daily_vol * math.sqrt(holding_period_days)
    return multiplier * period_vol


# =============================================================================
# Volatility Metrics (from Workbench)
# =============================================================================


def calculate_volatility_metrics(
    asset_id: str,
    price_history: list[float],
    btc_returns: list[float] | None = None,
    eth_returns: list[float] | None = None,
    spy_returns: list[float] | None = None,
) -> CryptoVolatilityMetrics:
    """Calculate comprehensive volatility metrics from price history.

    Args:
        asset_id: Asset identifier.
        price_history: Historical prices (most recent last).
        btc_returns: Optional BTC returns for correlation.
        eth_returns: Optional ETH returns for correlation.
        spy_returns: Optional S&P 500 returns for correlation.

    Returns:
        CryptoVolatilityMetrics with calculated values.
    """
    if len(price_history) < 2:
        raise ValueError("Need at least 2 price points")

    # Calculate log returns
    returns = []
    for i in range(1, len(price_history)):
        if price_history[i - 1] > 0:
            ret = math.log(price_history[i] / price_history[i - 1])
            returns.append(ret)

    if not returns:
        raise ValueError("Could not calculate returns from prices")

    def calc_vol(ret_slice: list[float]) -> float:
        if len(ret_slice) < 2:
            return 0.0
        mean = sum(ret_slice) / len(ret_slice)
        variance = sum((r - mean) ** 2 for r in ret_slice) / (len(ret_slice) - 1)
        daily_vol = math.sqrt(variance)
        return daily_vol * math.sqrt(365)

    vol_30d = calc_vol(returns[-30:]) if len(returns) >= 30 else calc_vol(returns)
    vol_90d = calc_vol(returns[-90:]) if len(returns) >= 90 else calc_vol(returns)

    var_95 = calculate_var(vol_30d, 0.95, 1)
    var_99 = calculate_var(vol_30d, 0.99, 1)
    cvar_95 = calculate_cvar(vol_30d, 0.95, 1)
    cvar_99 = calculate_cvar(vol_30d, 0.99, 1)

    # Max drawdown
    peak = price_history[0]
    max_dd = 0.0
    current_dd = 0.0
    for price in price_history:
        if price > peak:
            peak = price
        dd = (peak - price) / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)
        current_dd = dd

    # Correlations
    def calc_correlation(returns_a: list[float], returns_b: list[float]) -> float:
        n = min(len(returns_a), len(returns_b))
        if n < 10:
            return 0.0
        a = returns_a[-n:]
        b = returns_b[-n:]
        mean_a = sum(a) / n
        mean_b = sum(b) / n
        cov = sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(n)) / (n - 1)
        std_a = math.sqrt(sum((x - mean_a) ** 2 for x in a) / (n - 1))
        std_b = math.sqrt(sum((x - mean_b) ** 2 for x in b) / (n - 1))
        if std_a == 0 or std_b == 0:
            return 0.0
        return cov / (std_a * std_b)

    corr_btc = calc_correlation(returns, btc_returns) if btc_returns else 0.0
    corr_eth = calc_correlation(returns, eth_returns) if eth_returns else 0.0
    corr_spy = calc_correlation(returns, spy_returns) if spy_returns else 0.0

    return CryptoVolatilityMetrics(
        asset=asset_id,
        rolling_volatility_30d=vol_30d,
        rolling_volatility_90d=vol_90d,
        var_95=var_95,
        var_99=var_99,
        cvar_95=cvar_95,
        cvar_99=cvar_99,
        max_drawdown=max_dd,
        current_drawdown=current_dd,
        correlation_btc=corr_btc,
        correlation_eth=corr_eth,
        correlation_spy=corr_spy,
    )


# =============================================================================
# Liquidity Metrics (from Workbench)
# =============================================================================


def calculate_liquidity_metrics(
    asset_id: str,
    exchange: str,
    bid_ask_spread_bps: float,
    order_book_depth_usd: float,
    daily_volume_usd: float,
    bid_depth_usd: float | None = None,
    ask_depth_usd: float | None = None,
) -> LiquidityMetrics:
    """Calculate liquidity metrics and market impact estimates.

    Uses square-root market impact model for slippage estimation.
    """
    k = 0.1  # Market impact coefficient

    def estimate_slippage(order_size: float) -> float:
        if daily_volume_usd <= 0:
            return 10000  # 100% slippage if no volume
        impact = k * math.sqrt(order_size / daily_volume_usd)
        return (impact * 10000) + (bid_ask_spread_bps / 2)

    slippage_100k = estimate_slippage(100_000)
    slippage_1m = estimate_slippage(1_000_000)
    slippage_10m = estimate_slippage(10_000_000)

    # Composite liquidity score
    volume_score = min(50, 50 * math.log10(max(1, daily_volume_usd / 1_000_000) + 1) / 3)
    spread_score = max(0, 25 - bid_ask_spread_bps / 4)
    depth_score = min(25, 25 * math.log10(max(1, order_book_depth_usd / 100_000) + 1) / 2)
    liquidity_score = volume_score + spread_score + depth_score

    return LiquidityMetrics(
        asset=asset_id,
        exchange=exchange,
        bid_ask_spread_bps=bid_ask_spread_bps,
        order_book_depth_usd=order_book_depth_usd,
        bid_depth_usd=bid_depth_usd or order_book_depth_usd / 2,
        ask_depth_usd=ask_depth_usd or order_book_depth_usd / 2,
        daily_volume_usd=daily_volume_usd,
        slippage_estimate_100k=slippage_100k,
        slippage_estimate_1m=slippage_1m,
        slippage_estimate_10m=slippage_10m,
        liquidity_score=liquidity_score,
    )


# =============================================================================
# Risk Report Generation (from Workbench)
# =============================================================================


def generate_market_risk_report(
    asset_id: str,
    position_size_usd: float,
    volatility_metrics: CryptoVolatilityMetrics,
    liquidity_metrics: LiquidityMetrics | None = None,
    holding_period_days: int = 1,
) -> MarketRiskReport:
    """Generate comprehensive market risk report for a position."""
    risk_factors: list[str] = []
    recommendations: list[str] = []
    regulatory_flags: list[str] = []

    # Scale VaR to holding period
    var_95 = calculate_var(volatility_metrics.rolling_volatility_30d, 0.95, holding_period_days)
    var_99 = calculate_var(volatility_metrics.rolling_volatility_30d, 0.99, holding_period_days)
    cvar_95 = calculate_cvar(volatility_metrics.rolling_volatility_30d, 0.95, holding_period_days)

    var_95_usd = position_size_usd * var_95
    var_99_usd = position_size_usd * var_99
    cvar_95_usd = position_size_usd * cvar_95

    # Identify risk factors
    if volatility_metrics.rolling_volatility_30d > 1.0:
        risk_factors.append("Extreme volatility (>100% annualized)")
    elif volatility_metrics.rolling_volatility_30d > 0.6:
        risk_factors.append("High volatility (>60% annualized)")

    if volatility_metrics.max_drawdown > 0.5:
        risk_factors.append(f"Historical max drawdown of {volatility_metrics.max_drawdown:.0%}")

    if volatility_metrics.current_drawdown > 0.2:
        risk_factors.append(f"Currently in {volatility_metrics.current_drawdown:.0%} drawdown")

    if volatility_metrics.correlation_btc > 0.8:
        risk_factors.append("High BTC correlation - limited diversification benefit")

    if volatility_metrics.correlation_spy < -0.3:
        risk_factors.append("Negative equity correlation - potential hedge properties")

    # Liquidity risk factors
    if liquidity_metrics:
        if liquidity_metrics.slippage_estimate_1m > 100:
            risk_factors.append("High market impact for institutional sizes")
        if liquidity_metrics.daily_volume_usd < position_size_usd * 10:
            risk_factors.append("Position exceeds 10% of daily volume")
            recommendations.append("Consider executing over multiple days")
        if liquidity_metrics.bid_ask_spread_bps > 50:
            risk_factors.append("Wide bid-ask spread (>50 bps)")

    # Composite risk score (0-100)
    vol_component = min(40, volatility_metrics.rolling_volatility_30d * 40)
    dd_component = volatility_metrics.max_drawdown * 30
    liquidity_penalty = 0.0
    if liquidity_metrics and liquidity_metrics.liquidity_score < 50:
        liquidity_penalty = (50 - liquidity_metrics.liquidity_score) * 0.6

    risk_score = min(100, max(0, vol_component + dd_component + liquidity_penalty))

    # Risk rating
    if risk_score >= 75:
        risk_rating = RiskRating.EXTREME
        recommendations.append("Consider reducing position size")
        recommendations.append("Implement stop-loss orders")
    elif risk_score >= 50:
        risk_rating = RiskRating.HIGH
        recommendations.append("Monitor volatility daily")
        recommendations.append("Consider hedging strategies")
    elif risk_score >= 25:
        risk_rating = RiskRating.MEDIUM
        recommendations.append("Regular portfolio rebalancing recommended")
    else:
        risk_rating = RiskRating.LOW

    # Regulatory flags
    if position_size_usd > 10_000_000:
        regulatory_flags.append("Large position - may trigger reporting requirements")
    if var_99_usd > 1_000_000:
        regulatory_flags.append("Material VaR exposure - document risk management controls")

    return MarketRiskReport(
        asset=asset_id,
        position_size_usd=position_size_usd,
        holding_period_days=holding_period_days,
        volatility=volatility_metrics,
        liquidity=liquidity_metrics,
        var_95_usd=var_95_usd,
        var_99_usd=var_99_usd,
        cvar_95_usd=cvar_95_usd,
        risk_score=risk_score,
        risk_rating=risk_rating,
        risk_factors=risk_factors,
        recommendations=recommendations,
        regulatory_flags=regulatory_flags,
    )


# =============================================================================
# Portfolio-Level Stubs (from Console quant)
# =============================================================================


class MarketRiskService:
    """Unified market risk service combining Workbench calculations with Console portfolio stubs."""

    async def get_portfolio_var(self) -> VaRResponse:
        """Get portfolio-level Value at Risk calculations."""
        now = datetime.now(tz=UTC)
        return VaRResponse(
            results=[
                VaRResult(
                    portfolio_id="main_portfolio",
                    var_1d_95=1_500_000,
                    var_1d_99=2_500_000,
                    var_10d_99=7_900_000,
                    cvar_1d_99=3_200_000,
                    exposure_usd=150_000_000,
                    method="historical",
                    confidence_level=0.99,
                    calculated_at=now,
                ),
            ],
            total_portfolio_var_99=2_500_000,
            as_of=now,
        )

    async def get_stress_tests(self) -> StressTestResponse:
        """Get stress test results for various scenarios."""
        now = datetime.now(tz=UTC)
        return StressTestResponse(
            scenarios=[
                StressScenario(
                    scenario_name="March 2020 COVID Crash",
                    scenario_type="historical",
                    description="50% drawdown across crypto markets",
                    impact_usd=-75_000_000,
                    impact_percentage=-50.0,
                    probability=0.01,
                ),
                StressScenario(
                    scenario_name="Luna/Terra Collapse",
                    scenario_type="historical",
                    description="Stablecoin depeg and contagion",
                    impact_usd=-30_000_000,
                    impact_percentage=-20.0,
                    probability=0.02,
                ),
                StressScenario(
                    scenario_name="Ethereum Network Failure",
                    scenario_type="hypothetical",
                    description="Complete Ethereum network outage",
                    impact_usd=-50_000_000,
                    impact_percentage=-33.3,
                    probability=0.001,
                ),
                StressScenario(
                    scenario_name="Major Exchange Hack",
                    scenario_type="hypothetical",
                    description="Top 3 exchange compromised",
                    impact_usd=-20_000_000,
                    impact_percentage=-13.3,
                    probability=0.05,
                ),
            ],
            worst_case_impact_usd=-75_000_000,
            as_of=now,
        )

    async def get_correlations(self) -> CorrelationResponse:
        """Get asset correlation matrix."""
        now = datetime.now(tz=UTC)
        return CorrelationResponse(
            correlations=[
                CorrelationPair(
                    asset_a="BTC",
                    asset_b="ETH",
                    correlation_30d=0.85,
                    correlation_90d=0.82,
                    correlation_1y=0.80,
                ),
                CorrelationPair(
                    asset_a="BTC",
                    asset_b="SOL",
                    correlation_30d=0.72,
                    correlation_90d=0.70,
                    correlation_1y=0.68,
                ),
                CorrelationPair(
                    asset_a="ETH",
                    asset_b="SOL",
                    correlation_30d=0.78,
                    correlation_90d=0.75,
                    correlation_1y=0.72,
                ),
                CorrelationPair(
                    asset_a="BTC",
                    asset_b="SPY",
                    correlation_30d=0.45,
                    correlation_90d=0.42,
                    correlation_1y=0.38,
                ),
            ],
            window="30d",
            as_of=now,
        )

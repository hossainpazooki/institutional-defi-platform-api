"""Market risk API routes — unified /risk/* (Workbench) + /quant/* (Console) endpoints."""

from __future__ import annotations

import math
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query

from .schemas import (
    CorrelationResponse,
    MarketIntelligenceResponse,
    RiskAssessmentRequest,
    RiskAssessmentResponse,
    RiskRating,
    StressTestResponse,
    VaRCalculationRequest,
    VaRCalculationResponse,
    VaRResponse,
)
from .service import (
    MarketRiskService,
    calculate_cvar,
    calculate_liquidity_metrics,
    calculate_var,
    calculate_volatility_metrics,
    generate_market_risk_report,
)

risk_router = APIRouter(prefix="/risk", tags=["Market Risk"])
quant_router = APIRouter(prefix="/quant", tags=["Market Risk"])


# =============================================================================
# Demo Data
# =============================================================================

DEMO_PRICE_DATA: dict[str, list[float]] = {
    "BTC": [
        42000,
        43500,
        42800,
        44200,
        45000,
        44500,
        43800,
        45500,
        46200,
        45800,
        44900,
        46500,
        47200,
        46800,
        48000,
        47500,
        49000,
        48500,
        50000,
        49500,
        51000,
        50500,
        52000,
        51500,
        53000,
        52500,
        51800,
        53500,
        54000,
        53200,
    ],
    "ETH": [
        2200,
        2280,
        2240,
        2320,
        2400,
        2360,
        2300,
        2420,
        2500,
        2460,
        2380,
        2520,
        2600,
        2550,
        2680,
        2620,
        2750,
        2700,
        2850,
        2800,
        2920,
        2880,
        3000,
        2950,
        3100,
        3050,
        2980,
        3150,
        3200,
        3120,
    ],
    "SOL": [
        95,
        102,
        98,
        108,
        115,
        110,
        105,
        118,
        125,
        120,
        112,
        128,
        135,
        130,
        142,
        138,
        150,
        145,
        158,
        152,
        165,
        160,
        172,
        168,
        180,
        175,
        170,
        185,
        190,
        182,
    ],
    "USDC": [1.0] * 30,
}

DEMO_LIQUIDITY: dict[str, dict] = {
    "BTC": {"spread_bps": 5, "depth_usd": 50_000_000, "volume_usd": 25_000_000_000},
    "ETH": {"spread_bps": 8, "depth_usd": 30_000_000, "volume_usd": 15_000_000_000},
    "SOL": {"spread_bps": 15, "depth_usd": 10_000_000, "volume_usd": 2_000_000_000},
    "USDC": {"spread_bps": 2, "depth_usd": 100_000_000, "volume_usd": 50_000_000_000},
}

_service = MarketRiskService()


def _to_returns(prices: list[float]) -> list[float]:
    return [math.log(prices[i] / prices[i - 1]) for i in range(1, len(prices)) if prices[i - 1] > 0]


# =============================================================================
# /risk/* endpoints (from Workbench)
# =============================================================================


@risk_router.post("/assess", response_model=RiskAssessmentResponse)
async def assess_position_risk(request: RiskAssessmentRequest) -> RiskAssessmentResponse:
    """Assess market risk for a digital asset position."""
    asset = request.asset.upper()

    price_data = DEMO_PRICE_DATA.get(asset)
    if not price_data:
        raise HTTPException(
            status_code=404,
            detail=f"Asset {asset} not found. Available: {list(DEMO_PRICE_DATA.keys())}",
        )

    btc_returns = _to_returns(DEMO_PRICE_DATA["BTC"]) if asset != "BTC" else None
    eth_returns = _to_returns(DEMO_PRICE_DATA["ETH"]) if asset != "ETH" else None

    volatility_metrics = calculate_volatility_metrics(
        asset_id=asset,
        price_history=price_data,
        btc_returns=btc_returns,
        eth_returns=eth_returns,
    )

    liquidity_metrics = None
    if request.include_liquidity:
        liq = DEMO_LIQUIDITY.get(asset, DEMO_LIQUIDITY["SOL"])
        liquidity_metrics = calculate_liquidity_metrics(
            asset_id=asset,
            exchange="aggregated",
            bid_ask_spread_bps=liq["spread_bps"],
            order_book_depth_usd=liq["depth_usd"],
            daily_volume_usd=liq["volume_usd"],
        )

    report = generate_market_risk_report(
        asset_id=asset,
        position_size_usd=request.position_size_usd,
        volatility_metrics=volatility_metrics,
        liquidity_metrics=liquidity_metrics,
        holding_period_days=request.holding_period_days,
    )

    var_at_conf = calculate_var(
        volatility_metrics.rolling_volatility_30d,
        request.confidence_level,
        request.holding_period_days,
    )
    cvar_at_conf = calculate_cvar(
        volatility_metrics.rolling_volatility_30d,
        request.confidence_level,
        request.holding_period_days,
    )

    return RiskAssessmentResponse(
        asset=asset,
        position_size_usd=request.position_size_usd,
        holding_period_days=request.holding_period_days,
        var_95_pct=volatility_metrics.var_95,
        var_99_pct=volatility_metrics.var_99,
        var_usd=request.position_size_usd * var_at_conf,
        cvar_usd=request.position_size_usd * cvar_at_conf,
        risk_rating=report.risk_rating,
        risk_score=report.risk_score,
        volatility_30d=volatility_metrics.rolling_volatility_30d,
        max_drawdown=volatility_metrics.max_drawdown,
        key_risks=report.risk_factors,
        recommendations=report.recommendations,
        liquidity_score=liquidity_metrics.liquidity_score if liquidity_metrics else None,
        estimated_slippage_bps=liquidity_metrics.slippage_estimate_1m if liquidity_metrics else None,
    )


@risk_router.get("/market-intelligence/{asset}", response_model=MarketIntelligenceResponse)
async def get_market_intelligence(
    asset: str,
    include_regulatory: bool = Query(True, description="Include regulatory context"),
    include_correlations: bool = Query(True, description="Include correlation analysis"),
) -> MarketIntelligenceResponse:
    """Get market intelligence for a digital asset."""
    asset = asset.upper()

    price_data = DEMO_PRICE_DATA.get(asset)
    if not price_data:
        raise HTTPException(
            status_code=404,
            detail=f"Asset {asset} not found. Available: {list(DEMO_PRICE_DATA.keys())}",
        )

    btc_returns = _to_returns(DEMO_PRICE_DATA["BTC"]) if include_correlations and asset != "BTC" else None
    eth_returns = _to_returns(DEMO_PRICE_DATA["ETH"]) if include_correlations and asset != "ETH" else None

    volatility_metrics = calculate_volatility_metrics(
        asset_id=asset,
        price_history=price_data,
        btc_returns=btc_returns,
        eth_returns=eth_returns,
    )

    liq = DEMO_LIQUIDITY.get(asset, DEMO_LIQUIDITY["SOL"])
    liquidity_metrics = calculate_liquidity_metrics(
        asset_id=asset,
        exchange="aggregated",
        bid_ask_spread_bps=liq["spread_bps"],
        order_book_depth_usd=liq["depth_usd"],
        daily_volume_usd=liq["volume_usd"],
    )

    current_price = price_data[-1]
    change_24h = (price_data[-1] - price_data[-2]) / price_data[-2] if len(price_data) >= 2 else 0
    change_7d = (price_data[-1] - price_data[-7]) / price_data[-7] if len(price_data) >= 7 else 0
    change_30d = (price_data[-1] - price_data[0]) / price_data[0] if len(price_data) >= 30 else 0

    if volatility_metrics.rolling_volatility_30d > 1.0:
        risk_rating = RiskRating.EXTREME
    elif volatility_metrics.rolling_volatility_30d > 0.6:
        risk_rating = RiskRating.HIGH
    elif volatility_metrics.rolling_volatility_30d > 0.3:
        risk_rating = RiskRating.MEDIUM
    else:
        risk_rating = RiskRating.LOW

    regulatory_notes: list[str] = []
    if include_regulatory:
        if asset in ("BTC", "ETH"):
            regulatory_notes.append("Commodity treatment likely under CFTC jurisdiction")
        if asset == "USDC":
            regulatory_notes.append("Payment stablecoin - GENIUS Act compliance required")
            regulatory_notes.append("Reserve attestation requirements apply")
        if volatility_metrics.rolling_volatility_30d > 0.8:
            regulatory_notes.append("High volatility may trigger enhanced risk disclosures")

    return MarketIntelligenceResponse(
        asset=asset,
        timestamp=datetime.now(tz=UTC).isoformat(),
        current_price_usd=current_price,
        price_change_24h_pct=change_24h,
        price_change_7d_pct=change_7d,
        price_change_30d_pct=change_30d,
        volatility_30d=volatility_metrics.rolling_volatility_30d,
        volatility_90d=volatility_metrics.rolling_volatility_90d,
        correlation_btc=volatility_metrics.correlation_btc,
        correlation_eth=volatility_metrics.correlation_eth,
        correlation_spy=volatility_metrics.correlation_spy,
        var_95_1d=volatility_metrics.var_95,
        max_drawdown=volatility_metrics.max_drawdown,
        risk_rating=risk_rating,
        daily_volume_usd=liq["volume_usd"],
        liquidity_score=liquidity_metrics.liquidity_score,
        regulatory_notes=regulatory_notes,
    )


@risk_router.post("/calculate-var", response_model=VaRCalculationResponse)
async def calculate_var_endpoint(request: VaRCalculationRequest) -> VaRCalculationResponse:
    """Calculate Value at Risk and Conditional VaR directly."""
    var_pct = calculate_var(request.volatility, request.confidence_level, request.holding_period_days)
    cvar_pct = calculate_cvar(request.volatility, request.confidence_level, request.holding_period_days)

    return VaRCalculationResponse(
        var_pct=var_pct,
        var_usd=request.position_size_usd * var_pct,
        cvar_pct=cvar_pct,
        cvar_usd=request.position_size_usd * cvar_pct,
        inputs={
            "volatility": request.volatility,
            "position_size_usd": request.position_size_usd,
            "confidence_level": request.confidence_level,
            "holding_period_days": request.holding_period_days,
        },
    )


@risk_router.get("/supported-assets")
async def list_supported_assets() -> dict:
    """List all supported assets for risk analysis."""
    return {
        "assets": list(DEMO_PRICE_DATA.keys()),
        "note": "Demo data used for demonstration. Production would integrate with market data providers.",
    }


# =============================================================================
# /quant/* endpoints (from Console)
# =============================================================================


@quant_router.get("/var", response_model=VaRResponse)
async def get_var() -> VaRResponse:
    """Get portfolio-level Value at Risk calculations."""
    return await _service.get_portfolio_var()


@quant_router.get("/stress", response_model=StressTestResponse)
async def get_stress_tests() -> StressTestResponse:
    """Get stress test results for various scenarios."""
    return await _service.get_stress_tests()


@quant_router.get("/correlation", response_model=CorrelationResponse)
async def get_correlations() -> CorrelationResponse:
    """Get asset correlation matrix."""
    return await _service.get_correlations()


@quant_router.get("/volatility")
async def get_volatility() -> dict:
    """Get volatility metrics."""
    return {"status": "stub", "module": "quant.volatility"}


@quant_router.get("/greeks")
async def get_greeks() -> dict:
    """Get options Greeks exposure."""
    return {"status": "stub", "module": "quant.greeks"}


@quant_router.get("/liquidity")
async def get_liquidity() -> dict:
    """Get liquidity risk metrics."""
    return {"status": "stub", "module": "quant.liquidity"}

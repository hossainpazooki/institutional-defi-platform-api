"""Unified market risk schemas — VaR, CVaR, volatility, liquidity, stress tests, correlations."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RiskRating(StrEnum):
    """Risk rating classification."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    EXTREME = "EXTREME"


# ---------------------------------------------------------------------------
# Core metrics (from Workbench)
# ---------------------------------------------------------------------------


class CryptoVolatilityMetrics(BaseModel):
    """Volatility metrics for a cryptocurrency asset."""

    asset: str = Field(..., description="Asset identifier (e.g., BTC, ETH)")
    timestamp: datetime | None = None

    rolling_volatility_30d: float = Field(..., ge=0)
    rolling_volatility_90d: float = Field(0.0, ge=0)

    var_95: float = Field(..., description="95% 1-day VaR (percentage)")
    var_99: float = Field(..., description="99% 1-day VaR (percentage)")

    cvar_95: float = Field(..., description="95% Expected Shortfall (percentage)")
    cvar_99: float = Field(0.0, description="99% Expected Shortfall (percentage)")

    max_drawdown: float = Field(..., ge=0, le=1)
    current_drawdown: float = Field(0.0, ge=0, le=1)

    correlation_btc: float = Field(0.0, ge=-1, le=1)
    correlation_eth: float = Field(0.0, ge=-1, le=1)
    correlation_spy: float = Field(0.0, ge=-1, le=1)
    correlation_dxy: float = Field(0.0, ge=-1, le=1)


class LiquidityMetrics(BaseModel):
    """Liquidity metrics for a cryptocurrency on a specific exchange."""

    asset: str
    exchange: str
    timestamp: datetime | None = None

    bid_ask_spread_bps: float = Field(..., ge=0)
    order_book_depth_usd: float = Field(..., ge=0)
    bid_depth_usd: float = Field(0.0, ge=0)
    ask_depth_usd: float = Field(0.0, ge=0)

    daily_volume_usd: float = Field(..., ge=0)
    avg_trade_size_usd: float = Field(0.0, ge=0)

    slippage_estimate_100k: float = Field(0.0, ge=0)
    slippage_estimate_1m: float = Field(..., ge=0)
    slippage_estimate_10m: float = Field(0.0, ge=0)

    liquidity_score: float = Field(0.0, ge=0, le=100)


class MarketRiskReport(BaseModel):
    """Comprehensive market risk report for a digital asset position."""

    asset: str
    position_size_usd: float
    holding_period_days: int = 1
    timestamp: datetime | None = None

    volatility: CryptoVolatilityMetrics
    liquidity: LiquidityMetrics | None = None

    var_95_usd: float
    var_99_usd: float
    cvar_95_usd: float

    risk_score: float = Field(..., ge=0, le=100)
    risk_rating: RiskRating

    risk_factors: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    regulatory_flags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Router request/response (from Workbench /risk endpoints)
# ---------------------------------------------------------------------------


class RiskAssessmentRequest(BaseModel):
    """Request for position risk assessment."""

    asset: str = Field(..., description="Asset identifier (e.g., BTC, ETH, SOL)")
    position_size_usd: float = Field(..., gt=0)
    holding_period_days: int = Field(1, ge=1, le=365)
    confidence_level: float = Field(0.95, ge=0.90, le=0.99)
    include_liquidity: bool = Field(True)


class RiskAssessmentResponse(BaseModel):
    """Position risk assessment response."""

    asset: str
    position_size_usd: float
    holding_period_days: int

    var_95_pct: float
    var_99_pct: float
    var_usd: float
    cvar_usd: float

    risk_rating: RiskRating
    risk_score: float = Field(..., ge=0, le=100)

    volatility_30d: float
    max_drawdown: float
    key_risks: list[str]
    recommendations: list[str]

    liquidity_score: float | None = None
    estimated_slippage_bps: float | None = None


class MarketIntelligenceResponse(BaseModel):
    """Market intelligence for a digital asset."""

    asset: str
    timestamp: str

    current_price_usd: float
    price_change_24h_pct: float
    price_change_7d_pct: float
    price_change_30d_pct: float

    volatility_30d: float
    volatility_90d: float

    correlation_btc: float
    correlation_eth: float
    correlation_spy: float

    var_95_1d: float
    max_drawdown: float
    risk_rating: RiskRating

    daily_volume_usd: float
    liquidity_score: float

    regulatory_notes: list[str] = Field(default_factory=list)


class VaRCalculationRequest(BaseModel):
    """Direct VaR calculation request."""

    volatility: float = Field(..., gt=0, le=5.0)
    position_size_usd: float = Field(..., gt=0)
    confidence_level: float = Field(0.95, ge=0.90, le=0.99)
    holding_period_days: int = Field(1, ge=1, le=365)


class VaRCalculationResponse(BaseModel):
    """VaR calculation result."""

    var_pct: float
    var_usd: float
    cvar_pct: float
    cvar_usd: float
    inputs: dict[str, Any]


# ---------------------------------------------------------------------------
# Console quant schemas (merged under /quant prefix)
# ---------------------------------------------------------------------------


class VaRResult(BaseModel):
    """Portfolio-level Value at Risk calculation result."""

    portfolio_id: str
    var_1d_95: float
    var_1d_99: float
    var_10d_99: float
    cvar_1d_99: float
    exposure_usd: float
    method: str  # "historical", "parametric", "monte_carlo"
    confidence_level: float
    calculated_at: datetime


class VaRResponse(BaseModel):
    """Response model for portfolio VaR endpoint."""

    results: list[VaRResult]
    total_portfolio_var_99: float
    as_of: datetime


class StressScenario(BaseModel):
    """Stress test scenario result."""

    scenario_name: str
    scenario_type: str  # "historical", "hypothetical"
    description: str
    impact_usd: float
    impact_percentage: float
    probability: float | None = None


class StressTestResponse(BaseModel):
    """Response model for stress test endpoint."""

    scenarios: list[StressScenario]
    worst_case_impact_usd: float
    as_of: datetime


class CorrelationPair(BaseModel):
    """Correlation between two assets."""

    asset_a: str
    asset_b: str
    correlation_30d: float
    correlation_90d: float
    correlation_1y: float | None = None


class CorrelationResponse(BaseModel):
    """Response model for correlation endpoint."""

    correlations: list[CorrelationPair]
    window: str
    as_of: datetime

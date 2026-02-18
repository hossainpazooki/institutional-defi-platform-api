"""Pydantic schemas for Trading domain."""

from datetime import datetime

from pydantic import BaseModel


class ExposureItem(BaseModel):
    """Individual exposure entry."""

    asset: str
    chain: str
    exposure_usd: float
    percentage: float


class ExposureResponse(BaseModel):
    """Response model for exposure endpoint."""

    total_exposure_usd: float
    exposures: list[ExposureItem]
    as_of: datetime


class PnLItem(BaseModel):
    """P&L attribution item."""

    source: str
    pnl_usd: float
    pnl_percentage: float


class PnLResponse(BaseModel):
    """Response model for P&L endpoint."""

    total_pnl_usd: float
    total_pnl_percentage: float
    attribution: list[PnLItem]
    period: str
    as_of: datetime


class FundingRateItem(BaseModel):
    """Funding rate for a perpetual contract."""

    exchange: str
    symbol: str
    funding_rate: float
    next_funding_time: datetime
    predicted_rate: float | None = None


class FundingRatesResponse(BaseModel):
    """Response model for funding rates endpoint."""

    rates: list[FundingRateItem]
    as_of: datetime

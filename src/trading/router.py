"""Trading team API endpoints."""

from fastapi import APIRouter

from src.trading.schemas import (
    ExposureResponse,
    FundingRatesResponse,
    PnLResponse,
)
from src.trading.service import TradingService

router = APIRouter()

_service = TradingService()


@router.get("/exposure", response_model=ExposureResponse)
async def get_exposure() -> ExposureResponse:
    """Get current exposure matrix across assets and chains."""
    return await _service.get_exposure()


@router.get("/pnl", response_model=PnLResponse)
async def get_pnl() -> PnLResponse:
    """Get P&L attribution analysis."""
    return await _service.get_pnl()


@router.get("/funding", response_model=FundingRatesResponse)
async def get_funding_rates() -> FundingRatesResponse:
    """Get current funding rates across exchanges."""
    return await _service.get_funding_rates()


@router.get("/positions")
async def get_positions() -> dict[str, str]:
    """Get current trading positions."""
    return {"status": "stub", "module": "trading.positions"}


@router.get("/orders")
async def get_orders() -> dict[str, str]:
    """Get open orders."""
    return {"status": "stub", "module": "trading.orders"}

"""Trading domain business logic."""

from datetime import UTC, datetime

from src.trading.schemas import (
    ExposureItem,
    ExposureResponse,
    FundingRateItem,
    FundingRatesResponse,
    PnLItem,
    PnLResponse,
)


class TradingService:
    """Trading desk operations — exposure, P&L, funding rates."""

    async def get_exposure(self) -> ExposureResponse:
        """Get current exposure matrix across assets and chains."""
        now = datetime.now(tz=UTC)
        return ExposureResponse(
            total_exposure_usd=150_000_000,
            exposures=[
                ExposureItem(asset="ETH", chain="ethereum", exposure_usd=50_000_000, percentage=33.3),
                ExposureItem(asset="BTC", chain="bitcoin", exposure_usd=40_000_000, percentage=26.7),
                ExposureItem(asset="USDC", chain="base", exposure_usd=30_000_000, percentage=20.0),
                ExposureItem(asset="SOL", chain="solana", exposure_usd=20_000_000, percentage=13.3),
                ExposureItem(asset="MATIC", chain="polygon", exposure_usd=10_000_000, percentage=6.7),
            ],
            as_of=now,
        )

    async def get_pnl(self) -> PnLResponse:
        """Get P&L attribution analysis."""
        now = datetime.now(tz=UTC)
        return PnLResponse(
            total_pnl_usd=2_500_000,
            total_pnl_percentage=1.67,
            attribution=[
                PnLItem(source="spot_trading", pnl_usd=1_200_000, pnl_percentage=0.80),
                PnLItem(source="yield_farming", pnl_usd=800_000, pnl_percentage=0.53),
                PnLItem(source="funding_arb", pnl_usd=600_000, pnl_percentage=0.40),
                PnLItem(source="fees", pnl_usd=-100_000, pnl_percentage=-0.07),
            ],
            period="24h",
            as_of=now,
        )

    async def get_funding_rates(self) -> FundingRatesResponse:
        """Get current funding rates across exchanges."""
        now = datetime.now(tz=UTC)
        return FundingRatesResponse(
            rates=[
                FundingRateItem(
                    exchange="binance",
                    symbol="BTC-PERP",
                    funding_rate=0.0001,
                    next_funding_time=now,
                    predicted_rate=0.00012,
                ),
                FundingRateItem(
                    exchange="binance",
                    symbol="ETH-PERP",
                    funding_rate=0.00015,
                    next_funding_time=now,
                    predicted_rate=0.00018,
                ),
                FundingRateItem(
                    exchange="deribit",
                    symbol="BTC-PERP",
                    funding_rate=0.00008,
                    next_funding_time=now,
                ),
            ],
            as_of=now,
        )

"""
Instrument, activity, and investor type enums.

Unified from Workbench MiCA types and Console institutional types.
"""

from enum import StrEnum


class InstrumentType(StrEnum):
    """Types of crypto-assets and financial instruments."""

    # MiCA types (from Workbench)
    ART = "art"  # Asset-Referenced Token
    EMT = "emt"  # E-Money Token
    STABLECOIN = "stablecoin"
    UTILITY_TOKEN = "utility_token"
    OTHER_CRYPTO = "other_crypto"
    SECURITY_TOKEN = "security_token"
    NFT = "nft"

    # Institutional types (from Console JPM scenarios)
    GOVERNANCE_TOKEN = "governance_token"
    MONEY_MARKET_FUND = "money_market_fund"
    COMMERCIAL_PAPER = "commercial_paper"


class ActivityType(StrEnum):
    """Types of regulated activities."""

    PUBLIC_OFFER = "public_offer"
    ADMISSION_TO_TRADING = "admission_to_trading"
    CUSTODY = "custody"
    EXCHANGE = "exchange"
    EXECUTION = "execution"
    PLACEMENT = "placement"
    TRANSFER = "transfer"
    ADVICE = "advice"
    PORTFOLIO_MANAGEMENT = "portfolio_management"


class InvestorType(StrEnum):
    """Types of investors (from Console institutional classifications)."""

    RETAIL = "retail"
    PROFESSIONAL = "professional"
    INSTITUTIONAL = "institutional"
    QUALIFIED = "qualified"

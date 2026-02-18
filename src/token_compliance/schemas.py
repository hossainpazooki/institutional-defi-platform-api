"""Token compliance schemas.

Pydantic models for SEC Howey Test and GENIUS Act stablecoin analysis.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class TokenStandard(StrEnum):
    """Blockchain token standards."""

    ERC_20 = "erc_20"
    ERC_721 = "erc_721"
    ERC_1155 = "erc_1155"
    BEP_20 = "bep_20"
    SPL = "spl"
    TRC_20 = "trc_20"


class TokenClassification(StrEnum):
    """Regulatory classification for digital assets."""

    PAYMENT_STABLECOIN = "payment_stablecoin"
    SECURITY_TOKEN = "security_token"
    UTILITY_TOKEN = "utility_token"
    NFT = "nft"
    GOVERNANCE_TOKEN = "governance_token"
    COMMODITY_TOKEN = "commodity_token"


class HoweyProng(StrEnum):
    """The four prongs of the SEC Howey Test."""

    INVESTMENT_OF_MONEY = "investment_of_money"
    COMMON_ENTERPRISE = "common_enterprise"
    EXPECTATION_OF_PROFITS = "expectation_of_profits"
    EFFORTS_OF_OTHERS = "efforts_of_others"


class HoweyTestResult(BaseModel):
    """Result of SEC Howey Test analysis for security classification."""

    investment_of_money: bool = Field(..., description="Whether purchasers invested money or other consideration")
    common_enterprise: bool = Field(..., description="Whether there is horizontal or vertical commonality")
    expectation_of_profits: bool = Field(..., description="Whether purchasers have reasonable expectation of profits")
    efforts_of_others: bool = Field(..., description="Whether profits derive from efforts of promoter or third party")
    analysis_notes: list[str] = Field(default_factory=list)
    decentralization_factor: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Degree of decentralization (0=centralized, 1=fully decentralized)",
    )

    @property
    def is_security(self) -> bool:
        """Token is a security if all four Howey prongs are met."""
        return all(
            [
                self.investment_of_money,
                self.common_enterprise,
                self.expectation_of_profits,
                self.efforts_of_others,
            ]
        )

    @property
    def prongs_satisfied(self) -> int:
        """Count of Howey prongs satisfied."""
        return sum(
            [
                self.investment_of_money,
                self.common_enterprise,
                self.expectation_of_profits,
                self.efforts_of_others,
            ]
        )


class GeniusActAnalysis(BaseModel):
    """Analysis under the GENIUS Act for payment stablecoin classification."""

    is_payment_stablecoin: bool = Field(
        ..., description="Whether token qualifies as payment stablecoin under GENIUS Act"
    )
    backed_by_permitted_assets: bool = Field(..., description="Whether reserves consist of permitted assets")
    has_one_to_one_backing: bool = Field(..., description="Whether token maintains 1:1 reserve ratio")
    is_algorithmic: bool = Field(..., description="Whether token uses algorithmic stabilization (prohibited)")
    issuer_type: str = Field(..., description="Type of issuer: bank, non_bank_qualified, foreign")
    reserve_transparency: bool = Field(..., description="Whether issuer provides required reserve attestations")
    compliance_status: str = Field(..., description="compliant, non_compliant, requires_registration")
    compliance_notes: list[str] = Field(default_factory=list)

    @property
    def meets_genius_requirements(self) -> bool:
        """Check if stablecoin meets core GENIUS Act requirements."""
        return (
            self.is_payment_stablecoin
            and self.backed_by_permitted_assets
            and self.has_one_to_one_backing
            and not self.is_algorithmic
            and self.reserve_transparency
        )


class TokenComplianceResult(BaseModel):
    """Comprehensive compliance analysis result for a digital asset."""

    standard: TokenStandard
    classification: TokenClassification
    requires_sec_registration: bool
    genius_act_applicable: bool
    howey_analysis: HoweyTestResult | None = None
    genius_analysis: GeniusActAnalysis | None = None
    compliance_requirements: list[str] = Field(default_factory=list)
    regulatory_risks: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    sec_jurisdiction: bool = Field(False, description="Falls under SEC jurisdiction")
    cftc_jurisdiction: bool = Field(False, description="Falls under CFTC jurisdiction")


class HoweyTestRequest(BaseModel):
    """Request model for Howey Test analysis."""

    investment_of_money: bool = Field(..., description="Purchasers invested money or consideration")
    common_enterprise: bool = Field(..., description="Horizontal or vertical commonality exists")
    expectation_of_profits: bool = Field(..., description="Purchasers expect profits")
    efforts_of_others: bool = Field(..., description="Profits depend on promoter/third party efforts")
    decentralization_score: float = Field(0.0, ge=0.0, le=1.0, description="Degree of decentralization")
    is_functional_network: bool = Field(False, description="Whether network is functional and decentralized")


class GeniusActRequest(BaseModel):
    """Request model for GENIUS Act analysis."""

    is_stablecoin: bool = Field(..., description="Whether token is designed as stablecoin")
    pegged_currency: str = Field(
        "USD",
        min_length=1,
        max_length=10,
        pattern=r"^[A-Z]{3,10}$",
        description="Currency peg (USD, EUR, etc.)",
    )
    reserve_assets: list[str] = Field(
        default_factory=lambda: ["usd_cash"],
        max_length=20,
        description="List of reserve asset types",
    )
    reserve_ratio: float = Field(1.0, ge=0.0, le=10.0, description="Reserve-to-liability ratio")
    uses_algorithmic_mechanism: bool = Field(False, description="Whether uses algorithmic stabilization")
    issuer_charter_type: str = Field(
        "non_bank_qualified",
        pattern=r"^(bank|non_bank_qualified|foreign)$",
        description="bank, non_bank_qualified, or foreign",
    )
    has_reserve_attestation: bool = Field(False, description="Whether attestations are provided")
    attestation_frequency_days: int = Field(30, ge=0, le=365, description="Days between attestations")


class TokenComplianceRequest(BaseModel):
    """Request model for comprehensive token compliance analysis."""

    standard: TokenStandard
    has_profit_expectation: bool
    is_decentralized: bool
    backed_by_fiat: bool
    investment_of_money: bool = True
    common_enterprise: bool = True
    efforts_of_promoter: bool = True
    decentralization_score: float = Field(0.0, ge=0.0, le=1.0)
    is_functional_network: bool = False
    is_stablecoin: bool = False
    pegged_currency: str = Field("USD", min_length=1, max_length=10)
    reserve_assets: list[str] | None = Field(None, max_length=20)
    reserve_ratio: float = Field(1.0, ge=0.0, le=10.0)
    uses_algorithmic_mechanism: bool = False
    issuer_charter_type: str = Field(
        "non_bank_qualified",
        pattern=r"^(bank|non_bank_qualified|foreign)$",
    )
    has_reserve_attestation: bool = False
    attestation_frequency_days: int = Field(30, ge=0, le=365)

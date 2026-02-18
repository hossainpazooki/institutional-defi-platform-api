"""Scenario model for decision queries."""

from typing import Any

from pydantic import BaseModel, Field


class Scenario(BaseModel):
    """Input scenario for regulatory decision queries.

    A scenario represents a specific fact pattern to evaluate against rules.
    Fields are flexible to accommodate various rule types.

    Example:
        {
            "instrument_type": "stablecoin",
            "activity": "public_offer",
            "authorized": false,
            "jurisdiction": "EU",
            "issuer_type": "credit_institution"
        }
    """

    # Common fields with explicit typing
    instrument_type: str | None = None
    activity: str | None = None
    jurisdiction: str | None = None
    authorized: bool | None = None

    # Actor attributes
    actor_type: str | None = None
    issuer_type: str | None = None
    is_credit_institution: bool | None = None
    is_authorized_institution: bool | None = None

    # Instrument attributes
    reference_asset: str | None = None
    is_significant: bool | None = None
    reserve_value_eur: float | None = None

    # Reserve/custody attributes
    has_reserve: bool | None = None
    reserve_custodian_authorized: bool | None = None
    under_eba_supervision: bool | None = None
    enhanced_requirements_met: bool | None = None

    # RWA-specific attributes
    is_regulated_market_issuer: bool | None = None
    rwa_authorized: bool | None = None
    disclosure_current: bool | None = None
    total_token_value_eur: float | None = None
    custodian_authorized: bool | None = None
    assets_segregated: bool | None = None

    # Flexible additional fields
    extra: dict[str, Any] = Field(default_factory=dict)

    def get(self, field: str, default: Any = None) -> Any:
        """Get a field value, checking explicit fields first, then extra."""
        if hasattr(self, field) and field != "extra":
            value = getattr(self, field)
            if value is not None:
                return value
        return self.extra.get(field, default)

    def has(self, field: str) -> bool:
        """Check if a field exists and is not None."""
        if hasattr(self, field) and field != "extra":
            return getattr(self, field) is not None
        return field in self.extra

    def to_flat_dict(self) -> dict[str, Any]:
        """Convert to flat dictionary for rule evaluation."""
        result = {}
        for field_name in self.model_fields:
            if field_name == "extra":
                continue
            value = getattr(self, field_name)
            if value is not None:
                result[field_name] = value
        result.update(self.extra)
        return result

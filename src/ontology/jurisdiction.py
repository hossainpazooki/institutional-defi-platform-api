"""
Jurisdiction and regulatory regime types for multi-jurisdiction compliance.

These models support the v4 architecture for cross-border compliance navigation.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field


class JurisdictionCode(StrEnum):
    """Supported jurisdiction codes."""

    EU = "EU"
    US = "US"
    US_SEC = "US_SEC"  # SEC jurisdiction for securities
    US_CFTC = "US_CFTC"  # CFTC jurisdiction for derivatives/commodities
    UK = "UK"
    SG = "SG"
    CH = "CH"
    HK = "HK"  # Hong Kong
    JP = "JP"  # Japan


# Jurisdiction metadata
JURISDICTION_NAMES: dict[JurisdictionCode, str] = {
    JurisdictionCode.EU: "European Union",
    JurisdictionCode.UK: "United Kingdom",
    JurisdictionCode.US: "United States",
    JurisdictionCode.US_SEC: "United States (SEC)",
    JurisdictionCode.US_CFTC: "United States (CFTC)",
    JurisdictionCode.SG: "Singapore",
    JurisdictionCode.CH: "Switzerland",
    JurisdictionCode.HK: "Hong Kong",
    JurisdictionCode.JP: "Japan",
}

JURISDICTION_AUTHORITIES: dict[JurisdictionCode, str] = {
    JurisdictionCode.EU: "ESMA",
    JurisdictionCode.UK: "FCA",
    JurisdictionCode.US: "SEC",
    JurisdictionCode.US_SEC: "SEC",
    JurisdictionCode.US_CFTC: "CFTC",
    JurisdictionCode.SG: "MAS",
    JurisdictionCode.CH: "FINMA",
    JurisdictionCode.HK: "SFC",
    JurisdictionCode.JP: "JFSA",
}


class Jurisdiction(BaseModel):
    """Jurisdiction with regulatory authority (v4 spec)."""

    code: JurisdictionCode
    name: str
    authority: str  # ESMA, SEC, FCA, MAS, FINMA
    sub_jurisdiction: str | None = None  # EU member state, US state

    @classmethod
    def from_code(cls, code: JurisdictionCode | str) -> Jurisdiction:
        """Create Jurisdiction from code."""
        if isinstance(code, str):
            code = JurisdictionCode(code)
        return cls(
            code=code,
            name=JURISDICTION_NAMES.get(code, code.value),
            authority=JURISDICTION_AUTHORITIES.get(code, "Unknown"),
        )


class RegulatoryRegime(BaseModel):
    """A specific regulatory framework within a jurisdiction."""

    id: str  # mica_2023, fca_crypto_2024
    jurisdiction_code: JurisdictionCode
    name: str
    effective_date: date | None = None
    sunset_date: date | None = None
    source_url: str | None = None


class EquivalenceStatus(StrEnum):
    """Status of equivalence determination."""

    EQUIVALENT = "equivalent"
    PARTIAL = "partial"
    NOT_EQUIVALENT = "not_equivalent"
    PENDING = "pending"


class EquivalenceRef(BaseModel):
    """Cross-border equivalence reference (v4 spec)."""

    from_jurisdiction: JurisdictionCode
    to_jurisdiction: JurisdictionCode
    scope: str  # prospectus, authorization, custody
    status: EquivalenceStatus
    effective_date: date | None = None


class EquivalenceDetermination(BaseModel):
    """Full equivalence determination record."""

    id: str
    from_jurisdiction: JurisdictionCode
    to_jurisdiction: JurisdictionCode
    scope: str
    status: EquivalenceStatus
    effective_date: date | None = None
    expiry_date: date | None = None
    source_reference: str | None = None
    notes: str | None = None


class JurisdictionRole(StrEnum):
    """Role of a jurisdiction in cross-border scenario."""

    ISSUER_HOME = "issuer_home"
    TARGET = "target"
    PASSPORTING = "passporting"


class ApplicableJurisdiction(BaseModel):
    """Jurisdiction with role in cross-border scenario."""

    jurisdiction: JurisdictionCode
    regime_id: str
    role: JurisdictionRole


class ConflictType(StrEnum):
    """Types of cross-jurisdiction conflicts."""

    CLASSIFICATION = "classification_divergence"
    OBLIGATION = "obligation_conflict"
    TIMELINE = "timeline_conflict"
    DECISION = "decision_conflict"


class ConflictSeverity(StrEnum):
    """Severity of cross-jurisdiction conflicts."""

    BLOCKING = "blocking"
    WARNING = "warning"
    INFO = "info"


class RuleConflict(BaseModel):
    """Cross-jurisdiction rule conflict."""

    id: str
    rule_id_a: str
    rule_id_b: str
    conflict_type: ConflictType
    severity: ConflictSeverity
    description: str
    resolution_strategy: str | None = None  # cumulative, stricter, home_jurisdiction
    resolution_note: str | None = None
    jurisdictions: list[str] = Field(default_factory=list)

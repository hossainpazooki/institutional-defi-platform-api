"""Core domain types for regulatory knowledge modeling.

This module defines the ontology that mirrors how lawyers think about regulation:
- Provisions (legal text units)
- Normative content (Obligations, Permissions, Prohibitions)
- Regulated domain (Actors, Instruments, Activities)
- Conditions (applicability logic)
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from src.ontology.instrument import ActivityType, InstrumentType

# =============================================================================
# Source References
# =============================================================================


class SourceReference(BaseModel):
    """Pinpoint citation to source legal text."""

    document_id: str = Field(..., description="Document identifier (e.g., 'mica_2023')")
    article: str | None = Field(None, description="Article number (e.g., '36(1)')")
    section: str | None = Field(None, description="Section identifier")
    paragraph: int | None = Field(None, description="Paragraph number")
    pages: list[int] = Field(default_factory=list, description="Page numbers")
    text_excerpt: str | None = Field(None, description="Relevant text excerpt")


# =============================================================================
# Actors
# =============================================================================


class ActorType(StrEnum):
    """Types of regulated actors."""

    ISSUER = "issuer"
    OFFEROR = "offeror"
    TRADING_PLATFORM = "trading_platform"
    CUSTODIAN = "custodian"
    INVESTOR = "investor"
    COMPETENT_AUTHORITY = "competent_authority"
    OTHER = "other"


class Actor(BaseModel):
    """A regulated entity or person."""

    id: str
    type: ActorType
    name: str | None = None
    jurisdiction: str | None = Field(None, description="ISO country code or 'EU'")
    attributes: dict[str, str | bool | int] = Field(default_factory=dict)


# =============================================================================
# Instruments
# =============================================================================


class Instrument(BaseModel):
    """A financial instrument or crypto-asset."""

    id: str
    type: InstrumentType
    name: str | None = None
    reference_asset: str | None = Field(None, description="For ARTs: the referenced asset")
    issuer_id: str | None = None
    attributes: dict[str, str | bool | int | float] = Field(default_factory=dict)


# =============================================================================
# Activities
# =============================================================================


class Activity(BaseModel):
    """A regulated activity."""

    id: str
    type: ActivityType
    actor_id: str | None = None
    instrument_id: str | None = None
    jurisdiction: str | None = None
    attributes: dict[str, str | bool | int] = Field(default_factory=dict)


# =============================================================================
# Provisions
# =============================================================================


class ProvisionType(StrEnum):
    """Types of legal provisions."""

    DEFINITION = "definition"
    SCOPE = "scope"
    REQUIREMENT = "requirement"
    PROHIBITION = "prohibition"
    EXCEPTION = "exception"
    PROCEDURE = "procedure"
    SANCTION = "sanction"


class Provision(BaseModel):
    """A unit of legal text with semantic type."""

    id: str
    type: ProvisionType
    source: SourceReference
    text: str
    effective_from: date | None = None
    effective_to: date | None = None
    supersedes: str | None = Field(None, description="ID of provision this replaces")


# =============================================================================
# Normative Content (Obligations, Permissions, Prohibitions)
# =============================================================================


class Condition(BaseModel):
    """A condition for applicability of normative content."""

    field: str = Field(..., description="Field to evaluate (e.g., 'instrument_type')")
    operator: Literal["==", "!=", "in", "not_in", ">", "<", ">=", "<=", "exists"]
    value: str | int | float | bool | list[str] | None = None
    description: str | None = None


class ConditionGroup(BaseModel):
    """Logical grouping of conditions."""

    all: list[Condition | ConditionGroup] | None = None  # AND
    any: list[Condition | ConditionGroup] | None = None  # OR
    not_: Condition | ConditionGroup | None = Field(None, alias="not")  # NOT


class NormativeContent(BaseModel):
    """Base class for normative content."""

    id: str
    provision_id: str = Field(..., description="Source provision ID")
    applies_to_actor: ActorType | None = None
    applies_to_instrument: InstrumentType | None = None
    applies_to_activity: ActivityType | None = None
    conditions: ConditionGroup | None = None
    source: SourceReference | None = None


class Obligation(NormativeContent):
    """Something that MUST be done."""

    type: Literal["obligation"] = "obligation"
    action: str = Field(..., description="Required action")
    deadline: str | None = Field(None, description="Deadline specification")
    penalty_reference: str | None = None


class Permission(NormativeContent):
    """Something that MAY be done."""

    type: Literal["permission"] = "permission"
    action: str = Field(..., description="Permitted action")
    limits: str | None = Field(None, description="Limits on the permission")


class Prohibition(NormativeContent):
    """Something that MUST NOT be done."""

    type: Literal["prohibition"] = "prohibition"
    action: str = Field(..., description="Prohibited action")
    exceptions: list[str] = Field(default_factory=list, description="Exception IDs")


# Enable forward references for recursive types
ConditionGroup.model_rebuild()

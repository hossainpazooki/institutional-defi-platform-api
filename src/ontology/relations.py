"""Relation types for the regulatory knowledge graph."""

from enum import StrEnum

from pydantic import BaseModel, Field


class RelationType(StrEnum):
    """Types of relations between ontology entities."""

    # Normative relations
    IMPOSES_OBLIGATION_ON = "imposes_obligation_on"
    GRANTS_PERMISSION_TO = "grants_permission_to"
    PROHIBITS = "prohibits"

    # Structural relations
    DEFINES = "defines"
    REFERENCES = "references"
    SUPERSEDES = "supersedes"
    AMENDS = "amends"

    # Scope relations
    APPLIES_TO = "applies_to"
    EXEMPTS = "exempts"
    INCLUDES = "includes"
    EXCLUDES = "excludes"

    # Actor relations
    REGULATES = "regulates"
    AUTHORIZES = "authorizes"
    SUPERVISES = "supervises"

    # Instrument relations
    ISSUES = "issues"
    BACKS = "backs"
    REFERENCES_ASSET = "references_asset"


class Relation(BaseModel):
    """A typed relation between two entities."""

    id: str
    type: RelationType
    source_id: str = Field(..., description="ID of the source entity")
    target_id: str = Field(..., description="ID of the target entity")
    source_type: str = Field(..., description="Type of source (e.g., 'provision', 'actor')")
    target_type: str = Field(..., description="Type of target")
    attributes: dict[str, str | bool | int] = Field(default_factory=dict)
    provenance: str | None = Field(None, description="Source provision ID for this relation")

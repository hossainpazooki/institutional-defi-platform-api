"""Core ontology types for the regulatory knowledge platform."""

from src.ontology.instrument import ActivityType, InstrumentType, InvestorType
from src.ontology.jurisdiction import (
    ApplicableJurisdiction,
    Jurisdiction,
    JurisdictionCode,
    JurisdictionRole,
)
from src.ontology.relations import Relation, RelationType
from src.ontology.scenario import Scenario
from src.ontology.types import (
    Activity,
    Actor,
    ActorType,
    Condition,
    ConditionGroup,
    Instrument,
    NormativeContent,
    Obligation,
    Permission,
    Prohibition,
    Provision,
    ProvisionType,
    SourceReference,
)

__all__ = [
    # Instrument & Activity
    "ActivityType",
    "InstrumentType",
    "InvestorType",
    # Jurisdiction
    "ApplicableJurisdiction",
    "Jurisdiction",
    "JurisdictionCode",
    "JurisdictionRole",
    # Relations
    "Relation",
    "RelationType",
    # Scenario
    "Scenario",
    # Types
    "Activity",
    "Actor",
    "ActorType",
    "Condition",
    "ConditionGroup",
    "Instrument",
    "NormativeContent",
    "Obligation",
    "Permission",
    "Prohibition",
    "Provision",
    "ProvisionType",
    "SourceReference",
]

"""Jurisdiction domain — unified cross-border compliance navigation.

Merges:
- Workbench jurisdiction/ (service layer)
- Workbench rules/jurisdiction/ (resolver, conflicts, pathway, evaluator)
- Console compliance/ (regulatory status, sanctions)
"""

from .conflicts import check_timeline_conflicts, detect_conflicts
from .evaluator import (
    evaluate_jurisdiction,
    evaluate_jurisdiction_sync,
    evaluate_multiple_jurisdictions,
)
from .pathway import (
    aggregate_obligations,
    estimate_timeline,
    get_critical_path,
    synthesize_pathway,
)
from .repository import JurisdictionConfigRepository
from .resolver import (
    get_equivalences,
    get_jurisdiction_info,
    get_regime_info,
    resolve_jurisdictions,
)
from .router import compliance_router, navigate_router
from .schemas import (
    ComplianceAlert,
    JurisdictionInfo,
    JurisdictionRoleResponse,
    JurisdictionsResponse,
    NavigateRequest,
    NavigateResponse,
    SanctionCheckResult,
    SanctionsResponse,
)

__all__ = [
    # Routers
    "navigate_router",
    "compliance_router",
    # Resolver
    "resolve_jurisdictions",
    "get_equivalences",
    "get_jurisdiction_info",
    "get_regime_info",
    # Conflicts
    "detect_conflicts",
    "check_timeline_conflicts",
    # Pathway
    "synthesize_pathway",
    "aggregate_obligations",
    "estimate_timeline",
    "get_critical_path",
    # Evaluator
    "evaluate_jurisdiction",
    "evaluate_multiple_jurisdictions",
    "evaluate_jurisdiction_sync",
    # Repository
    "JurisdictionConfigRepository",
    # Navigate Schemas
    "NavigateRequest",
    "NavigateResponse",
    "JurisdictionRoleResponse",
    # Compliance Schemas
    "JurisdictionInfo",
    "JurisdictionsResponse",
    "SanctionCheckResult",
    "SanctionsResponse",
    "ComplianceAlert",
]

"""Jurisdiction service layer — cross-border compliance resolution and evaluation.

Thin orchestration layer delegating to resolver, conflicts, pathway, and evaluator.
From Workbench jurisdiction/service.py.
"""

from __future__ import annotations

from .conflicts import (
    check_timeline_conflicts,
    detect_conflicts,
)
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
from .resolver import (
    get_equivalences,
    get_jurisdiction_info,
    get_regime_info,
    resolve_jurisdictions,
)

__all__ = [
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
]

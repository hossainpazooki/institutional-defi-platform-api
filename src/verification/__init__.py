"""Verification domain — 5-tier semantic consistency checking for rules."""

from .service import (
    ConsistencyEngine,
    check_actor_mentioned,
    check_date_consistency,
    check_decision_tree_valid,
    check_deontic_alignment,
    check_exception_coverage,
    check_id_format,
    check_instrument_mentioned,
    check_keyword_overlap,
    check_negation_consistency,
    check_required_fields,
    check_schema_valid,
    check_source_exists,
    compute_summary,
    verify_rule,
)

__all__ = [
    "ConsistencyEngine",
    "check_actor_mentioned",
    "check_date_consistency",
    "check_decision_tree_valid",
    "check_deontic_alignment",
    "check_exception_coverage",
    "check_id_format",
    "check_instrument_mentioned",
    "check_keyword_overlap",
    "check_negation_consistency",
    "check_required_fields",
    "check_schema_valid",
    "check_source_exists",
    "compute_summary",
    "verify_rule",
]

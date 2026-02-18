"""Jurisdiction domain constants.

Constants for cross-border compliance resolution, conflict detection, and pathway synthesis.
Extracted from Workbench jurisdiction/service.py, rules/jurisdiction/pathway.py, and
rules/jurisdiction/conflicts.py.
"""

from __future__ import annotations

from typing import Any

# =============================================================================
# Resolver Constants
# =============================================================================

DEFAULT_REGIMES: dict[str, str] = {
    "EU": "mica_2023",
    "UK": "fca_crypto_2024",
    "US": "genius_act_2025",
    "US_SEC": "securities_act_1933",
    "US_CFTC": "cftc_digital_assets_2024",
    "CH": "finsa_dlt_2021",
    "SG": "psa_2019",
    "HK": "sfc_vasp_2023",
    "JP": "psa_japan_2023",
}


# =============================================================================
# Conflict Constants
# =============================================================================

EXCLUSIVE_OBLIGATION_PAIRS: dict[frozenset[str], dict[str, str]] = {
    frozenset(["implement_cooling_off", "immediate_execution"]): {
        "description": "UK requires 24h cooling off vs immediate execution allowed elsewhere",
        "resolution": "Apply cooling off for UK-targeted offers",
    },
    frozenset(["submit_whitepaper", "no_disclosure"]): {
        "description": "Whitepaper requirement conflicts with minimal disclosure regime",
        "resolution": "Prepare whitepaper to satisfy stricter requirement",
    },
    frozenset(["add_risk_warning", "no_warning_required"]): {
        "description": "Risk warning requirement conflicts with no-warning jurisdiction",
        "resolution": "Add risk warning to satisfy stricter requirement",
    },
}


# =============================================================================
# Pathway Constants
# =============================================================================

STEP_TIMELINES: dict[str, dict[str, Any]] = {
    "obtain_authorization": {
        "min_days": 90,
        "max_days": 180,
        "description": "Full authorization process",
    },
    "obtain_fca_authorization": {
        "min_days": 90,
        "max_days": 180,
        "description": "FCA authorization",
    },
    "submit_whitepaper": {
        "min_days": 1,
        "max_days": 20,
        "description": "Whitepaper submission and review",
    },
    "add_risk_warning": {
        "min_days": 1,
        "max_days": 5,
        "description": "Add required disclosures",
    },
    "implement_cooling_off": {
        "min_days": 5,
        "max_days": 30,
        "description": "Technical implementation",
    },
    "conduct_assessment": {
        "min_days": 1,
        "max_days": 10,
        "description": "Appropriateness assessment implementation",
    },
    "mas_license": {
        "min_days": 60,
        "max_days": 120,
        "description": "MAS licensing process",
    },
    "finma_authorization": {
        "min_days": 90,
        "max_days": 180,
        "description": "FINMA authorization",
    },
    "maintain_approval_records": {
        "min_days": 1,
        "max_days": 5,
        "description": "Record-keeping setup",
    },
    "mlr_registration_check": {
        "min_days": 1,
        "max_days": 5,
        "description": "MLR registration verification",
    },
}

STEP_DEPENDENCIES: dict[str, list[str]] = {
    "submit_whitepaper": ["obtain_authorization"],
    "eu_passporting": ["obtain_authorization", "submit_whitepaper"],
    "uk_promotion": ["obtain_fca_authorization"],
    "add_risk_warning": [],
    "implement_cooling_off": ["add_risk_warning"],
    "conduct_assessment": ["implement_cooling_off"],
}

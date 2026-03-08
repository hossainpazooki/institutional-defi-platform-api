"""Jurisdiction resolver for cross-border compliance.

Resolves applicable jurisdictions and regimes based on issuer location
and target markets. From Workbench rules/jurisdiction/resolver.py.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from src.database import get_db
from src.ontology.jurisdiction import (
    ApplicableJurisdiction,
    JurisdictionCode,
    JurisdictionRole,
)

from .constants import DEFAULT_REGIMES


def resolve_jurisdictions(
    issuer: str,
    targets: list[str],
    instrument_type: str | None = None,
) -> list[ApplicableJurisdiction]:
    """Resolve applicable jurisdictions for a cross-border scenario."""
    applicable = []

    issuer_code = issuer if isinstance(issuer, str) else issuer.value
    applicable.append(
        ApplicableJurisdiction(
            jurisdiction=JurisdictionCode(issuer_code),
            regime_id=_get_regime_for_jurisdiction(issuer_code, instrument_type),
            role=JurisdictionRole.ISSUER_HOME,
        )
    )

    for target in targets:
        target_code = target if isinstance(target, str) else target.value
        if target_code != issuer_code:
            applicable.append(
                ApplicableJurisdiction(
                    jurisdiction=JurisdictionCode(target_code),
                    regime_id=_get_regime_for_jurisdiction(target_code, instrument_type),
                    role=JurisdictionRole.TARGET,
                )
            )

    return applicable


def _get_regime_for_jurisdiction(
    jurisdiction_code: str,
    instrument_type: str | None = None,
) -> str:
    """Get the default regulatory regime for a jurisdiction."""
    return DEFAULT_REGIMES.get(jurisdiction_code, "unknown")


def get_equivalences(
    from_jurisdiction: str,
    to_jurisdictions: list[str],
) -> list[dict[str, Any]]:
    """Get equivalence determinations between jurisdictions."""
    if not to_jurisdictions:
        return []

    equivalences = []

    try:
        with get_db() as conn:
            target_params = {f"target_{i}": t for i, t in enumerate(to_jurisdictions)}
            placeholders = ", ".join(f":target_{i}" for i in range(len(to_jurisdictions)))

            result = conn.execute(
                text(f"""
                SELECT id, from_jurisdiction, to_jurisdiction, scope, status,
                       effective_date, expiry_date, source_reference, notes
                FROM equivalence_determinations
                WHERE from_jurisdiction = :from_j
                  AND to_jurisdiction IN ({placeholders})
                """),
                {"from_j": from_jurisdiction, **target_params},
            )

            for row in result.fetchall():
                equivalences.append(
                    {
                        "id": row[0],
                        "from": row[1],
                        "to": row[2],
                        "scope": row[3],
                        "status": row[4],
                        "effective_date": row[5],
                        "expiry_date": row[6],
                        "source_reference": row[7],
                        "notes": row[8],
                    }
                )

            result = conn.execute(
                text(f"""
                SELECT id, from_jurisdiction, to_jurisdiction, scope, status,
                       effective_date, expiry_date, source_reference, notes
                FROM equivalence_determinations
                WHERE to_jurisdiction = :from_j
                  AND from_jurisdiction IN ({placeholders})
                """),
                {"from_j": from_jurisdiction, **target_params},
            )

            for row in result.fetchall():
                equivalences.append(
                    {
                        "id": row[0],
                        "from": row[1],
                        "to": row[2],
                        "scope": row[3],
                        "status": row[4],
                        "effective_date": row[5],
                        "expiry_date": row[6],
                        "source_reference": row[7],
                        "notes": row[8],
                    }
                )
    except Exception:
        pass

    return equivalences


def get_jurisdiction_info(code: str) -> dict[str, Any] | None:
    """Get jurisdiction information from database."""
    try:
        with get_db() as conn:
            result = conn.execute(
                text("""
                SELECT code, name, authority, parent_code
                FROM jurisdictions
                WHERE code = :code
                """),
                {"code": code},
            )
            row = result.fetchone()
            if row:
                return {
                    "code": row[0],
                    "name": row[1],
                    "authority": row[2],
                    "parent_code": row[3],
                }
    except Exception:
        pass
    return None


def get_regime_info(regime_id: str) -> dict[str, Any] | None:
    """Get regulatory regime information from database."""
    try:
        with get_db() as conn:
            result = conn.execute(
                text("""
                SELECT id, jurisdiction_code, name, effective_date, sunset_date, source_url
                FROM regulatory_regimes
                WHERE id = :regime_id
                """),
                {"regime_id": regime_id},
            )
            row = result.fetchone()
            if row:
                return {
                    "id": row[0],
                    "jurisdiction_code": row[1],
                    "name": row[2],
                    "effective_date": row[3],
                    "sunset_date": row[4],
                    "source_url": row[5],
                }
    except Exception:
        pass
    return None

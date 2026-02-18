"""Jurisdiction configuration repository.

Provides CRUD operations for jurisdiction-specific configurations,
replacing hardcoded dictionaries in pathway.py and conflicts.py.
From Workbench storage/stores/jurisdiction_config_repo.py.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from src.database import get_db


class JurisdictionConfigRepository:
    """Repository for jurisdiction configuration data.

    Manages:
    - Step timelines for compliance pathways
    - Step dependencies
    - Obligation conflict pairs
    """

    # =========================================================================
    # Step Timeline Operations
    # =========================================================================

    def get_step_timeline(self, step_id: str, jurisdiction_code: str = "*") -> dict[str, Any] | None:
        """Get timeline for a specific step and jurisdiction."""
        with get_db() as conn:
            result = conn.execute(
                text("""
                SELECT step_id, jurisdiction_code, min_days, max_days, description
                FROM step_timelines
                WHERE step_id = :step_id AND jurisdiction_code = :jurisdiction_code
                """),
                {"step_id": step_id, "jurisdiction_code": jurisdiction_code},
            )
            row = result.fetchone()

            if not row and jurisdiction_code != "*":
                result = conn.execute(
                    text("""
                    SELECT step_id, jurisdiction_code, min_days, max_days, description
                    FROM step_timelines
                    WHERE step_id = :step_id AND jurisdiction_code = '*'
                    """),
                    {"step_id": step_id},
                )
                row = result.fetchone()

            if row:
                return {
                    "step_id": row[0],
                    "jurisdiction_code": row[1],
                    "min_days": row[2],
                    "max_days": row[3],
                    "description": row[4],
                }
            return None

    def get_all_step_timelines(self, jurisdiction_code: str | None = None) -> list[dict[str, Any]]:
        """Get all step timelines."""
        with get_db() as conn:
            if jurisdiction_code:
                result = conn.execute(
                    text("""
                    SELECT step_id, jurisdiction_code, min_days, max_days, description
                    FROM step_timelines
                    WHERE jurisdiction_code = :jurisdiction_code
                    ORDER BY step_id
                    """),
                    {"jurisdiction_code": jurisdiction_code},
                )
            else:
                result = conn.execute(
                    text("""
                    SELECT step_id, jurisdiction_code, min_days, max_days, description
                    FROM step_timelines
                    ORDER BY step_id, jurisdiction_code
                    """)
                )

            return [
                {
                    "step_id": row[0],
                    "jurisdiction_code": row[1],
                    "min_days": row[2],
                    "max_days": row[3],
                    "description": row[4],
                }
                for row in result.fetchall()
            ]

    def set_step_timeline(
        self,
        step_id: str,
        min_days: int,
        max_days: int,
        jurisdiction_code: str = "*",
        description: str | None = None,
    ) -> None:
        """Set or update a step timeline."""
        with get_db() as conn:
            conn.execute(
                text("""
                INSERT INTO step_timelines
                (step_id, jurisdiction_code, min_days, max_days, description)
                VALUES (:step_id, :jurisdiction_code, :min_days, :max_days, :description)
                ON CONFLICT (step_id, jurisdiction_code) DO UPDATE SET
                    min_days = :min_days,
                    max_days = :max_days,
                    description = :description
                """),
                {
                    "step_id": step_id,
                    "jurisdiction_code": jurisdiction_code,
                    "min_days": min_days,
                    "max_days": max_days,
                    "description": description,
                },
            )
            conn.commit()

    # =========================================================================
    # Step Dependency Operations
    # =========================================================================

    def get_step_dependencies(self, step_id: str) -> list[str]:
        """Get dependencies for a step."""
        with get_db() as conn:
            result = conn.execute(
                text("""
                SELECT depends_on FROM step_dependencies
                WHERE step_id = :step_id
                ORDER BY depends_on
                """),
                {"step_id": step_id},
            )
            return [row[0] for row in result.fetchall()]

    def get_all_dependencies(self) -> dict[str, list[str]]:
        """Get all step dependencies."""
        with get_db() as conn:
            result = conn.execute(
                text("""
                SELECT step_id, depends_on FROM step_dependencies
                ORDER BY step_id, depends_on
                """)
            )

            deps: dict[str, list[str]] = {}
            for row in result.fetchall():
                step_id = row[0]
                if step_id not in deps:
                    deps[step_id] = []
                deps[step_id].append(row[1])

            return deps

    def set_step_dependency(self, step_id: str, depends_on: str) -> None:
        """Add a step dependency."""
        with get_db() as conn:
            conn.execute(
                text("""
                INSERT INTO step_dependencies (step_id, depends_on)
                VALUES (:step_id, :depends_on)
                ON CONFLICT DO NOTHING
                """),
                {"step_id": step_id, "depends_on": depends_on},
            )
            conn.commit()

    def remove_step_dependency(self, step_id: str, depends_on: str) -> bool:
        """Remove a step dependency."""
        with get_db() as conn:
            result = conn.execute(
                text("""
                DELETE FROM step_dependencies
                WHERE step_id = :step_id AND depends_on = :depends_on
                """),
                {"step_id": step_id, "depends_on": depends_on},
            )
            conn.commit()
            return result.rowcount > 0

    # =========================================================================
    # Obligation Conflict Operations
    # =========================================================================

    def get_obligation_conflicts(self, obligation: str) -> list[dict[str, Any]]:
        """Get conflicts for a specific obligation."""
        with get_db() as conn:
            result = conn.execute(
                text("""
                SELECT obligation_a, obligation_b, conflict_type, severity, resolution_hint
                FROM obligation_conflicts
                WHERE obligation_a = :obligation OR obligation_b = :obligation
                ORDER BY obligation_a, obligation_b
                """),
                {"obligation": obligation},
            )

            return [
                {
                    "obligation_a": row[0],
                    "obligation_b": row[1],
                    "conflict_type": row[2],
                    "severity": row[3],
                    "resolution_hint": row[4],
                }
                for row in result.fetchall()
            ]

    def get_all_obligation_conflicts(self) -> list[dict[str, Any]]:
        """Get all obligation conflicts."""
        with get_db() as conn:
            result = conn.execute(
                text("""
                SELECT obligation_a, obligation_b, conflict_type, severity, resolution_hint
                FROM obligation_conflicts
                ORDER BY obligation_a, obligation_b
                """)
            )

            return [
                {
                    "obligation_a": row[0],
                    "obligation_b": row[1],
                    "conflict_type": row[2],
                    "severity": row[3],
                    "resolution_hint": row[4],
                }
                for row in result.fetchall()
            ]

    def are_obligations_conflicting(self, obligation_a: str, obligation_b: str) -> dict[str, Any] | None:
        """Check if two obligations conflict."""
        a, b = sorted([obligation_a, obligation_b])

        with get_db() as conn:
            result = conn.execute(
                text("""
                SELECT obligation_a, obligation_b, conflict_type, severity, resolution_hint
                FROM obligation_conflicts
                WHERE obligation_a = :a AND obligation_b = :b
                """),
                {"a": a, "b": b},
            )
            row = result.fetchone()

            if row:
                return {
                    "obligation_a": row[0],
                    "obligation_b": row[1],
                    "conflict_type": row[2],
                    "severity": row[3],
                    "resolution_hint": row[4],
                }
            return None

    def set_obligation_conflict(
        self,
        obligation_a: str,
        obligation_b: str,
        conflict_type: str,
        severity: str,
        resolution_hint: str | None = None,
    ) -> None:
        """Set or update an obligation conflict."""
        a, b = sorted([obligation_a, obligation_b])

        with get_db() as conn:
            conn.execute(
                text("""
                INSERT INTO obligation_conflicts
                (obligation_a, obligation_b, conflict_type, severity, resolution_hint)
                VALUES (:a, :b, :conflict_type, :severity, :resolution_hint)
                ON CONFLICT (obligation_a, obligation_b) DO UPDATE SET
                    conflict_type = :conflict_type,
                    severity = :severity,
                    resolution_hint = :resolution_hint
                """),
                {
                    "a": a,
                    "b": b,
                    "conflict_type": conflict_type,
                    "severity": severity,
                    "resolution_hint": resolution_hint,
                },
            )
            conn.commit()

    # =========================================================================
    # Seed Operations
    # =========================================================================

    def seed_defaults(self) -> None:
        """Seed default configuration values from hardcoded constants."""
        default_timelines = [
            ("classify_instrument", 5, 15, "Initial instrument classification"),
            ("determine_jurisdiction", 3, 10, "Jurisdiction determination"),
            ("prepare_whitepaper", 30, 90, "Whitepaper preparation"),
            ("submit_authorization", 60, 180, "Authorization submission"),
            ("nca_review", 90, 270, "NCA review period"),
            ("ongoing_compliance", 0, 0, "Ongoing compliance (continuous)"),
        ]

        for step_id, min_days, max_days, description in default_timelines:
            self.set_step_timeline(step_id, min_days, max_days, "*", description)

        default_dependencies = [
            ("determine_jurisdiction", "classify_instrument"),
            ("prepare_whitepaper", "classify_instrument"),
            ("submit_authorization", "prepare_whitepaper"),
            ("submit_authorization", "determine_jurisdiction"),
            ("nca_review", "submit_authorization"),
            ("ongoing_compliance", "nca_review"),
        ]

        for step_id, depends_on in default_dependencies:
            self.set_step_dependency(step_id, depends_on)

        default_conflicts = [
            (
                "exempt",
                "authorized",
                "classification",
                "blocking",
                "A token cannot be both exempt and require authorization",
            ),
            ("custodial", "self_custodial", "custody", "blocking", "Custody model must be one or the other"),
            ("prospectus_required", "prospectus_exempt", "disclosure", "blocking", "Prospectus requirement is binary"),
        ]

        for obl_a, obl_b, conflict_type, severity, hint in default_conflicts:
            self.set_obligation_conflict(obl_a, obl_b, conflict_type, severity, hint)

"""Rule repository for database operations.

Provides CRUD operations for rules, including IR storage and premise index management.
"""

from __future__ import annotations

import json

import yaml
from sqlalchemy import text

from src.database import get_db
from src.rules.models import (
    RuleRecord,
    now_iso,
)


class RuleRepository:
    """Repository for rule persistence operations."""

    # =========================================================================
    # Rule CRUD
    # =========================================================================

    def save_rule(
        self,
        rule_id: str,
        content_yaml: str,
        source_document_id: str | None = None,
        source_article: str | None = None,
    ) -> RuleRecord:
        """Save or update a rule."""
        try:
            parsed = yaml.safe_load(content_yaml)
            content_json = json.dumps(parsed)
        except yaml.YAMLError:
            content_json = None

        with get_db() as conn:
            result = conn.execute(
                text("SELECT id, version FROM rules WHERE rule_id = :rule_id"),
                {"rule_id": rule_id},
            )
            existing = result.fetchone()

            if existing:
                record = RuleRecord(
                    id=existing[0],
                    rule_id=rule_id,
                    version=existing[1],
                    content_yaml=content_yaml,
                    content_json=content_json,
                    source_document_id=source_document_id,
                    source_article=source_article,
                    updated_at=now_iso(),
                )
                conn.execute(
                    text("""
                    UPDATE rules SET
                        content_yaml = :content_yaml,
                        content_json = :content_json,
                        source_document_id = :source_document_id,
                        source_article = :source_article,
                        updated_at = :updated_at,
                        rule_ir = NULL,
                        compiled_at = NULL
                    WHERE id = :id
                    """),
                    {
                        "content_yaml": content_yaml,
                        "content_json": content_json,
                        "source_document_id": source_document_id,
                        "source_article": source_article,
                        "updated_at": record.updated_at,
                        "id": record.id,
                    },
                )
            else:
                record = RuleRecord(
                    rule_id=rule_id,
                    content_yaml=content_yaml,
                    content_json=content_json,
                    source_document_id=source_document_id,
                    source_article=source_article,
                )
                conn.execute(
                    text("""
                    INSERT INTO rules (
                        id, rule_id, version, content_yaml, content_json,
                        source_document_id, source_article, created_at, updated_at, is_active
                    ) VALUES (:id, :rule_id, :version, :content_yaml, :content_json,
                              :source_document_id, :source_article, :created_at, :updated_at, :is_active)
                    """),
                    {
                        "id": record.id,
                        "rule_id": record.rule_id,
                        "version": record.version,
                        "content_yaml": record.content_yaml,
                        "content_json": record.content_json,
                        "source_document_id": record.source_document_id,
                        "source_article": record.source_article,
                        "created_at": record.created_at,
                        "updated_at": record.updated_at,
                        "is_active": 1,
                    },
                )

            conn.commit()
            return record

    def get_rule(self, rule_id: str) -> RuleRecord | None:
        """Get a rule by ID."""
        with get_db() as conn:
            result = conn.execute(
                text("SELECT * FROM rules WHERE rule_id = :rule_id AND is_active = 1"),
                {"rule_id": rule_id},
            )
            row = result.fetchone()
            if row:
                return RuleRecord.from_row(dict(row._mapping))
            return None

    def get_all_rules(self, active_only: bool = True) -> list[RuleRecord]:
        """Get all rules."""
        with get_db() as conn:
            if active_only:
                result = conn.execute(text("SELECT * FROM rules WHERE is_active = 1 ORDER BY rule_id"))
            else:
                result = conn.execute(text("SELECT * FROM rules ORDER BY rule_id"))
            return [RuleRecord.from_row(dict(row._mapping)) for row in result.fetchall()]

    def delete_rule(self, rule_id: str, soft: bool = True) -> bool:
        """Delete a rule (soft delete by default)."""
        with get_db() as conn:
            if soft:
                result = conn.execute(
                    text("UPDATE rules SET is_active = 0, updated_at = :updated_at WHERE rule_id = :rule_id"),
                    {"updated_at": now_iso(), "rule_id": rule_id},
                )
            else:
                result = conn.execute(
                    text("DELETE FROM rules WHERE rule_id = :rule_id"),
                    {"rule_id": rule_id},
                )
            conn.commit()
            return result.rowcount > 0

    # =========================================================================
    # IR Operations
    # =========================================================================

    def update_rule_ir(self, rule_id: str, rule_ir: str, ir_version: int = 1) -> bool:
        """Update the compiled IR for a rule."""
        with get_db() as conn:
            result = conn.execute(
                text("""
                UPDATE rules SET
                    rule_ir = :rule_ir,
                    ir_version = :ir_version,
                    compiled_at = :compiled_at,
                    updated_at = :updated_at
                WHERE rule_id = :rule_id AND is_active = 1
                """),
                {
                    "rule_ir": rule_ir,
                    "ir_version": ir_version,
                    "compiled_at": now_iso(),
                    "updated_at": now_iso(),
                    "rule_id": rule_id,
                },
            )
            conn.commit()
            return result.rowcount > 0

    def get_rule_ir(self, rule_id: str) -> str | None:
        """Get the compiled IR for a rule."""
        with get_db() as conn:
            result = conn.execute(
                text("SELECT rule_ir FROM rules WHERE rule_id = :rule_id AND is_active = 1"),
                {"rule_id": rule_id},
            )
            row = result.fetchone()
            if row:
                return str(row[0])
            return None

    def get_rules_needing_compilation(self) -> list[str]:
        """Get rule IDs that need compilation."""
        with get_db() as conn:
            result = conn.execute(
                text("""
                SELECT rule_id FROM rules
                WHERE is_active = 1 AND (rule_ir IS NULL OR compiled_at < updated_at)
                ORDER BY rule_id
                """)
            )
            return [str(row[0]) for row in result.fetchall()]

    # =========================================================================
    # Premise Index Operations
    # =========================================================================

    def update_premise_index(self, rule_id: str, premise_keys: list[str], rule_version: int = 1) -> None:
        """Update the premise index for a rule."""
        with get_db() as conn:
            conn.execute(
                text("DELETE FROM rule_premise_index WHERE rule_id = :rule_id AND rule_version = :rule_version"),
                {"rule_id": rule_id, "rule_version": rule_version},
            )
            for position, key in enumerate(premise_keys):
                conn.execute(
                    text("""
                    INSERT INTO rule_premise_index (
                        premise_key, rule_id, rule_version, premise_position, selectivity
                    ) VALUES (:premise_key, :rule_id, :rule_version, :premise_position, :selectivity)
                    """),
                    {
                        "premise_key": key,
                        "rule_id": rule_id,
                        "rule_version": rule_version,
                        "premise_position": position,
                        "selectivity": 0.5,
                    },
                )
            conn.commit()

    def get_rules_by_premise(self, premise_key: str) -> list[str]:
        """Get rule IDs that match a premise key."""
        with get_db() as conn:
            result = conn.execute(
                text("""
                SELECT DISTINCT rpi.rule_id
                FROM rule_premise_index rpi
                JOIN rules r ON rpi.rule_id = r.rule_id
                WHERE rpi.premise_key = :premise_key AND r.is_active = 1
                ORDER BY rpi.rule_id
                """),
                {"premise_key": premise_key},
            )
            return [str(row[0]) for row in result.fetchall()]

    def get_rules_by_premises(self, premise_keys: list[str]) -> list[str]:
        """Get rule IDs that match ALL premise keys (intersection)."""
        if not premise_keys:
            return []

        with get_db() as conn:
            key_params = {f"key_{i}": k for i, k in enumerate(premise_keys)}
            placeholders = ", ".join(f":key_{i}" for i in range(len(premise_keys)))

            result = conn.execute(
                text(f"""
                SELECT rpi.rule_id
                FROM rule_premise_index rpi
                JOIN rules r ON rpi.rule_id = r.rule_id
                WHERE rpi.premise_key IN ({placeholders}) AND r.is_active = 1
                GROUP BY rpi.rule_id
                HAVING COUNT(DISTINCT rpi.premise_key) = :num_keys
                ORDER BY rpi.rule_id
                """),
                {**key_params, "num_keys": len(premise_keys)},
            )
            return [str(row[0]) for row in result.fetchall()]

    def get_all_premise_keys(self) -> list[str]:
        """Get all unique premise keys in the index."""
        with get_db() as conn:
            result = conn.execute(text("SELECT DISTINCT premise_key FROM rule_premise_index ORDER BY premise_key"))
            return [str(row[0]) for row in result.fetchall()]

    # =========================================================================
    # Query Operations
    # =========================================================================

    def get_rules_by_document(self, document_id: str) -> list[RuleRecord]:
        """Get all rules from a specific document."""
        with get_db() as conn:
            result = conn.execute(
                text("""
                SELECT * FROM rules
                WHERE source_document_id = :document_id AND is_active = 1
                ORDER BY source_article, rule_id
                """),
                {"document_id": document_id},
            )
            return [RuleRecord.from_row(dict(row._mapping)) for row in result.fetchall()]

    def count_rules(self, active_only: bool = True) -> int:
        """Count total rules."""
        with get_db() as conn:
            if active_only:
                result = conn.execute(text("SELECT COUNT(*) as count FROM rules WHERE is_active = 1"))
            else:
                result = conn.execute(text("SELECT COUNT(*) as count FROM rules"))
            row = result.fetchone()
            return int(row[0]) if row else 0

    def count_compiled_rules(self) -> int:
        """Count rules with compiled IR."""
        with get_db() as conn:
            result = conn.execute(
                text("SELECT COUNT(*) as count FROM rules WHERE is_active = 1 AND rule_ir IS NOT NULL")
            )
            row = result.fetchone()
            return int(row[0]) if row else 0

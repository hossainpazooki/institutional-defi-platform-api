"""Rule version repository for temporal versioning operations."""

from __future__ import annotations

import hashlib
import json

import yaml
from sqlalchemy import text

from src.database import get_db
from src.rules.models import RuleVersionRecord, now_iso


class RuleVersionRepository:
    """Repository for rule version persistence operations."""

    def create_version(
        self,
        rule_id: str,
        content_yaml: str,
        effective_from: str | None = None,
        effective_to: str | None = None,
        created_by: str | None = None,
        jurisdiction_code: str | None = None,
        regime_id: str | None = None,
    ) -> RuleVersionRecord:
        """Create a new rule version."""
        content_hash = hashlib.sha256(content_yaml.encode()).hexdigest()[:16]

        try:
            parsed = yaml.safe_load(content_yaml)
            content_json = json.dumps(parsed)
        except yaml.YAMLError:
            content_json = None

        with get_db() as conn:
            result = conn.execute(
                text("SELECT MAX(version) as max_version FROM rule_versions WHERE rule_id = :rule_id"),
                {"rule_id": rule_id},
            )
            row = result.fetchone()
            next_version = (row[0] or 0) + 1

            if next_version > 1:
                conn.execute(
                    text("""
                    UPDATE rule_versions
                    SET superseded_by = :superseded_by, superseded_at = :superseded_at
                    WHERE rule_id = :rule_id AND version = :version
                    """),
                    {
                        "superseded_by": next_version,
                        "superseded_at": now_iso(),
                        "rule_id": rule_id,
                        "version": next_version - 1,
                    },
                )

            record = RuleVersionRecord(
                rule_id=rule_id,
                version=next_version,
                content_yaml=content_yaml,
                content_json=content_json,
                content_hash=content_hash,
                effective_from=effective_from,
                effective_to=effective_to,
                created_by=created_by,
                jurisdiction_code=jurisdiction_code,
                regime_id=regime_id,
            )

            conn.execute(
                text("""
                INSERT INTO rule_versions (
                    id, rule_id, version, content_yaml, content_json, content_hash,
                    effective_from, effective_to, created_at, created_by,
                    jurisdiction_code, regime_id
                ) VALUES (:id, :rule_id, :version, :content_yaml, :content_json, :content_hash,
                          :effective_from, :effective_to, :created_at, :created_by,
                          :jurisdiction_code, :regime_id)
                """),
                {
                    "id": record.id,
                    "rule_id": record.rule_id,
                    "version": record.version,
                    "content_yaml": record.content_yaml,
                    "content_json": record.content_json,
                    "content_hash": record.content_hash,
                    "effective_from": record.effective_from,
                    "effective_to": record.effective_to,
                    "created_at": record.created_at,
                    "created_by": record.created_by,
                    "jurisdiction_code": record.jurisdiction_code,
                    "regime_id": record.regime_id,
                },
            )

            conn.commit()
            return record

    def get_version(self, rule_id: str, version: int) -> RuleVersionRecord | None:
        """Get a specific version of a rule."""
        with get_db() as conn:
            result = conn.execute(
                text("SELECT * FROM rule_versions WHERE rule_id = :rule_id AND version = :version"),
                {"rule_id": rule_id, "version": version},
            )
            row = result.fetchone()
            if row:
                return RuleVersionRecord.from_row(row._mapping)
            return None

    def get_latest_version(self, rule_id: str) -> RuleVersionRecord | None:
        """Get the latest version of a rule."""
        with get_db() as conn:
            result = conn.execute(
                text("""
                SELECT * FROM rule_versions
                WHERE rule_id = :rule_id
                ORDER BY version DESC
                LIMIT 1
                """),
                {"rule_id": rule_id},
            )
            row = result.fetchone()
            if row:
                return RuleVersionRecord.from_row(row._mapping)
            return None

    def get_version_at_timestamp(self, rule_id: str, timestamp: str) -> RuleVersionRecord | None:
        """Get the version effective at a specific timestamp."""
        with get_db() as conn:
            result = conn.execute(
                text("""
                SELECT * FROM rule_versions
                WHERE rule_id = :rule_id
                  AND (effective_from IS NULL OR effective_from <= :ts)
                  AND (effective_to IS NULL OR effective_to > :ts)
                ORDER BY version DESC
                LIMIT 1
                """),
                {"rule_id": rule_id, "ts": timestamp},
            )
            row = result.fetchone()
            if row:
                return RuleVersionRecord.from_row(row._mapping)

            result = conn.execute(
                text("""
                SELECT * FROM rule_versions
                WHERE rule_id = :rule_id AND created_at <= :ts
                ORDER BY version DESC
                LIMIT 1
                """),
                {"rule_id": rule_id, "ts": timestamp},
            )
            row = result.fetchone()
            if row:
                return RuleVersionRecord.from_row(row._mapping)
            return None

    def get_version_history(self, rule_id: str, limit: int = 100) -> list[RuleVersionRecord]:
        """Get the version history for a rule."""
        with get_db() as conn:
            result = conn.execute(
                text("""
                SELECT * FROM rule_versions
                WHERE rule_id = :rule_id
                ORDER BY version DESC
                LIMIT :limit
                """),
                {"rule_id": rule_id, "limit": limit},
            )
            return [RuleVersionRecord.from_row(row._mapping) for row in result.fetchall()]

    def get_versions_by_hash(self, content_hash: str) -> list[RuleVersionRecord]:
        """Get all versions with a specific content hash."""
        with get_db() as conn:
            result = conn.execute(
                text("SELECT * FROM rule_versions WHERE content_hash = :content_hash ORDER BY rule_id, version"),
                {"content_hash": content_hash},
            )
            return [RuleVersionRecord.from_row(row._mapping) for row in result.fetchall()]

    def get_all_rule_ids(self) -> list[str]:
        """Get all unique rule IDs with versions."""
        with get_db() as conn:
            result = conn.execute(text("SELECT DISTINCT rule_id FROM rule_versions ORDER BY rule_id"))
            return [row[0] for row in result.fetchall()]

    def count_versions(self, rule_id: str | None = None) -> int:
        """Count versions."""
        with get_db() as conn:
            if rule_id:
                result = conn.execute(
                    text("SELECT COUNT(*) as count FROM rule_versions WHERE rule_id = :rule_id"),
                    {"rule_id": rule_id},
                )
            else:
                result = conn.execute(text("SELECT COUNT(*) as count FROM rule_versions"))
            return result.fetchone()[0]

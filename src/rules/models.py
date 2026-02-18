"""Data models for rules persistence layer.

Uses dataclasses for lightweight, serialization-friendly record types.
These mirror the database schema and can be converted to/from Pydantic models.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())


def now_iso() -> str:
    """Get current time as ISO 8601 string."""
    return datetime.now(UTC).isoformat()


# =============================================================================
# Temporal Versioning Types
# =============================================================================


class RuleEventType(StrEnum):
    """Types of rule lifecycle events."""

    RULE_CREATED = "RuleCreated"
    RULE_UPDATED = "RuleUpdated"
    RULE_DEPRECATED = "RuleDeprecated"


@dataclass
class RuleVersionRecord:
    """Immutable snapshot of a rule version."""

    rule_id: str
    version: int
    content_yaml: str
    content_hash: str
    id: str = field(default_factory=generate_uuid)
    content_json: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    created_at: str = field(default_factory=now_iso)
    created_by: str | None = None
    superseded_by: int | None = None
    superseded_at: str | None = None
    jurisdiction_code: str | None = None
    regime_id: str | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> RuleVersionRecord:
        """Create from database row."""
        return cls(
            id=row["id"],
            rule_id=row["rule_id"],
            version=row["version"],
            content_yaml=row["content_yaml"],
            content_json=row.get("content_json"),
            content_hash=row["content_hash"],
            effective_from=row.get("effective_from"),
            effective_to=row.get("effective_to"),
            created_at=row["created_at"],
            created_by=row.get("created_by"),
            superseded_by=row.get("superseded_by"),
            superseded_at=row.get("superseded_at"),
            jurisdiction_code=row.get("jurisdiction_code"),
            regime_id=row.get("regime_id"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database insertion."""
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "version": self.version,
            "content_yaml": self.content_yaml,
            "content_json": self.content_json,
            "content_hash": self.content_hash,
            "effective_from": self.effective_from,
            "effective_to": self.effective_to,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "superseded_by": self.superseded_by,
            "superseded_at": self.superseded_at,
            "jurisdiction_code": self.jurisdiction_code,
            "regime_id": self.regime_id,
        }


@dataclass
class RuleEventRecord:
    """Event sourcing record for rule changes."""

    rule_id: str
    version: int
    event_type: str
    event_data: str  # JSON
    id: str = field(default_factory=generate_uuid)
    sequence_number: int | None = None
    timestamp: str = field(default_factory=now_iso)
    actor: str | None = None
    reason: str | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> RuleEventRecord:
        """Create from database row."""
        return cls(
            id=row["id"],
            sequence_number=row["sequence_number"],
            rule_id=row["rule_id"],
            version=row["version"],
            event_type=row["event_type"],
            event_data=row["event_data"],
            timestamp=row["timestamp"],
            actor=row.get("actor"),
            reason=row.get("reason"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database insertion."""
        return {
            "id": self.id,
            "sequence_number": self.sequence_number,
            "rule_id": self.rule_id,
            "version": self.version,
            "event_type": self.event_type,
            "event_data": self.event_data,
            "timestamp": self.timestamp,
            "actor": self.actor,
            "reason": self.reason,
        }


# =============================================================================
# Rule Record
# =============================================================================


@dataclass
class RuleRecord:
    """Database record for a rule."""

    rule_id: str
    content_yaml: str
    id: str = field(default_factory=generate_uuid)
    version: int = 1
    content_json: str | None = None
    rule_ir: str | None = None
    ir_version: int = 1
    compiled_at: str | None = None
    source_document_id: str | None = None
    source_article: str | None = None
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    is_active: bool = True

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> RuleRecord:
        """Create from database row."""
        return cls(
            id=row["id"],
            rule_id=row["rule_id"],
            version=row["version"],
            content_yaml=row["content_yaml"],
            content_json=row["content_json"],
            rule_ir=row["rule_ir"],
            ir_version=row["ir_version"] or 1,
            compiled_at=row["compiled_at"],
            source_document_id=row["source_document_id"],
            source_article=row["source_article"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            is_active=bool(row["is_active"]),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database insertion."""
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "version": self.version,
            "content_yaml": self.content_yaml,
            "content_json": self.content_json,
            "rule_ir": self.rule_ir,
            "ir_version": self.ir_version,
            "compiled_at": self.compiled_at,
            "source_document_id": self.source_document_id,
            "source_article": self.source_article,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "is_active": 1 if self.is_active else 0,
        }


# =============================================================================
# Premise Index Record
# =============================================================================


@dataclass
class PremiseIndexRecord:
    """Database record for premise index entries."""

    premise_key: str  # e.g., "instrument_type:art"
    rule_id: str
    rule_version: int = 1
    premise_position: int | None = None
    selectivity: float = 0.5

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> PremiseIndexRecord:
        """Create from database row."""
        return cls(
            premise_key=row["premise_key"],
            rule_id=row["rule_id"],
            rule_version=row["rule_version"],
            premise_position=row["premise_position"],
            selectivity=row["selectivity"],
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database insertion."""
        return {
            "premise_key": self.premise_key,
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "premise_position": self.premise_position,
            "selectivity": self.selectivity,
        }

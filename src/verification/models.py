"""Verification database record models."""

from __future__ import annotations

import contextlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def _generate_uuid() -> str:
    return str(uuid.uuid4())


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class VerificationResultRecord:
    """Database record for verification results."""

    rule_id: str
    status: str  # verified, needs_review, inconsistent, unverified
    id: str = field(default_factory=_generate_uuid)
    rule_version: int = 1
    confidence: float | None = None
    verified_at: str = field(default_factory=_now_iso)
    verified_by: str | None = None
    notes: str | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> VerificationResultRecord:
        return cls(
            id=row["id"],
            rule_id=row["rule_id"],
            rule_version=row["rule_version"],
            status=row["status"],
            confidence=row["confidence"],
            verified_at=row["verified_at"],
            verified_by=row["verified_by"],
            notes=row["notes"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "status": self.status,
            "confidence": self.confidence,
            "verified_at": self.verified_at,
            "verified_by": self.verified_by,
            "notes": self.notes,
        }


@dataclass
class VerificationEvidenceRecord:
    """Database record for verification evidence."""

    verification_id: str
    tier: int
    category: str
    label: str  # pass, fail, warning
    id: str = field(default_factory=_generate_uuid)
    score: float | None = None
    details: str | None = None
    source_span: str | None = None
    rule_element: str | None = None
    created_at: str = field(default_factory=_now_iso)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> VerificationEvidenceRecord:
        return cls(
            id=row["id"],
            verification_id=row["verification_id"],
            tier=row["tier"],
            category=row["category"],
            label=row["label"],
            score=row["score"],
            details=row["details"],
            source_span=row["source_span"],
            rule_element=row["rule_element"],
            created_at=row["created_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "verification_id": self.verification_id,
            "tier": self.tier,
            "category": self.category,
            "label": self.label,
            "score": self.score,
            "details": self.details,
            "source_span": self.source_span,
            "rule_element": self.rule_element,
            "created_at": self.created_at,
        }


@dataclass
class ReviewRecord:
    """Database record for human reviews."""

    rule_id: str
    reviewer_id: str
    decision: str  # consistent, inconsistent, unknown
    id: str = field(default_factory=_generate_uuid)
    notes: str | None = None
    created_at: str = field(default_factory=_now_iso)
    metadata: dict[str, Any] | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> ReviewRecord:
        metadata = None
        if row["metadata"]:
            with contextlib.suppress(json.JSONDecodeError):
                metadata = json.loads(row["metadata"])

        return cls(
            id=row["id"],
            rule_id=row["rule_id"],
            reviewer_id=row["reviewer_id"],
            decision=row["decision"],
            notes=row["notes"],
            created_at=row["created_at"],
            metadata=metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "reviewer_id": self.reviewer_id,
            "decision": self.decision,
            "notes": self.notes,
            "created_at": self.created_at,
            "metadata": json.dumps(self.metadata) if self.metadata else None,
        }

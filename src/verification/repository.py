"""Verification repository for database operations."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from src.database import get_db

from .models import (
    ReviewRecord,
    VerificationEvidenceRecord,
    VerificationResultRecord,
    _generate_uuid,
    _now_iso,
)


class VerificationRepository:
    """Repository for verification persistence operations."""

    # =========================================================================
    # Verification Results
    # =========================================================================

    def save_verification_result(
        self,
        rule_id: str,
        status: str,
        confidence: float | None = None,
        verified_by: str | None = None,
        notes: str | None = None,
        evidence: list[dict[str, Any]] | None = None,
    ) -> VerificationResultRecord:
        """Save a verification result with optional evidence."""
        with get_db() as conn:
            result = conn.execute(
                text("SELECT id FROM verification_results WHERE rule_id = :rule_id"),
                {"rule_id": rule_id},
            )
            existing = result.fetchone()
            result_id: str = str(existing[0]) if existing else _generate_uuid()

            if existing:
                conn.execute(
                    text("""
                    UPDATE verification_results SET
                        status = :status, confidence = :confidence,
                        verified_at = :verified_at, verified_by = :verified_by,
                        notes = :notes
                    WHERE id = :id
                    """),
                    {
                        "status": status,
                        "confidence": confidence,
                        "verified_at": _now_iso(),
                        "verified_by": verified_by,
                        "notes": notes,
                        "id": result_id,
                    },
                )
                conn.execute(
                    text("DELETE FROM verification_evidence WHERE verification_id = :vid"),
                    {"vid": result_id},
                )
            else:
                conn.execute(
                    text("""
                    INSERT INTO verification_results (
                        id, rule_id, rule_version, status, confidence,
                        verified_at, verified_by, notes
                    ) VALUES (:id, :rule_id, :rule_version, :status, :confidence,
                              :verified_at, :verified_by, :notes)
                    """),
                    {
                        "id": result_id,
                        "rule_id": rule_id,
                        "rule_version": 1,
                        "status": status,
                        "confidence": confidence,
                        "verified_at": _now_iso(),
                        "verified_by": verified_by,
                        "notes": notes,
                    },
                )

            if evidence:
                for ev in evidence:
                    conn.execute(
                        text("""
                        INSERT INTO verification_evidence (
                            id, verification_id, tier, category, label,
                            score, details, source_span, rule_element, created_at
                        ) VALUES (:id, :verification_id, :tier, :category, :label,
                                  :score, :details, :source_span, :rule_element, :created_at)
                        """),
                        {
                            "id": _generate_uuid(),
                            "verification_id": result_id,
                            "tier": ev.get("tier", 0),
                            "category": ev.get("category", "unknown"),
                            "label": ev.get("label", "warning"),
                            "score": ev.get("score"),
                            "details": ev.get("details"),
                            "source_span": ev.get("source_span"),
                            "rule_element": ev.get("rule_element"),
                            "created_at": _now_iso(),
                        },
                    )

            conn.commit()

            return VerificationResultRecord(
                id=result_id,
                rule_id=rule_id,
                status=status,
                confidence=confidence,
                verified_by=verified_by,
                notes=notes,
            )

    def get_verification_result(
        self, rule_id: str
    ) -> tuple[VerificationResultRecord | None, list[VerificationEvidenceRecord]]:
        with get_db() as conn:
            result = conn.execute(
                text("SELECT * FROM verification_results WHERE rule_id = :rule_id"),
                {"rule_id": rule_id},
            )
            row = result.fetchone()
            if not row:
                return None, []

            record = VerificationResultRecord.from_row(dict(row._mapping))

            result = conn.execute(
                text("""
                SELECT * FROM verification_evidence
                WHERE verification_id = :vid ORDER BY tier, category
                """),
                {"vid": record.id},
            )
            evidence = [VerificationEvidenceRecord.from_row(dict(ev._mapping)) for ev in result.fetchall()]
            return record, evidence

    def get_all_verification_results(
        self,
    ) -> dict[str, tuple[VerificationResultRecord, list[VerificationEvidenceRecord]]]:
        with get_db() as conn:
            result = conn.execute(text("SELECT * FROM verification_results ORDER BY rule_id"))
            results = {}
            for row in result.fetchall():
                results[dict(row._mapping)["rule_id"]] = VerificationResultRecord.from_row(dict(row._mapping))

            result = conn.execute(
                text("""
                SELECT ve.*, vr.rule_id
                FROM verification_evidence ve
                JOIN verification_results vr ON ve.verification_id = vr.id
                ORDER BY vr.rule_id, ve.tier, ve.category
                """)
            )

            evidence_by_rule: dict[str, list[VerificationEvidenceRecord]] = {}
            for row in result.fetchall():
                rid = dict(row._mapping)["rule_id"]
                if rid not in evidence_by_rule:
                    evidence_by_rule[rid] = []
                evidence_by_rule[rid].append(VerificationEvidenceRecord.from_row(dict(row._mapping)))

            return {rid: (rec, evidence_by_rule.get(rid, [])) for rid, rec in results.items()}

    def delete_verification_result(self, rule_id: str) -> bool:
        with get_db() as conn:
            result = conn.execute(
                text("DELETE FROM verification_results WHERE rule_id = :rule_id"),
                {"rule_id": rule_id},
            )
            conn.commit()
            return bool(result.rowcount > 0)

    # =========================================================================
    # Statistics
    # =========================================================================

    def get_verification_stats(self) -> dict[str, int]:
        with get_db() as conn:
            result = conn.execute(text("SELECT status, COUNT(*) as count FROM verification_results GROUP BY status"))
            return {str(row[0]): int(row[1]) for row in result.fetchall()}

    def get_evidence_stats(self) -> dict[str, dict[str, int]]:
        with get_db() as conn:
            result = conn.execute(
                text("""
                SELECT tier, label, COUNT(*) as count
                FROM verification_evidence GROUP BY tier, label
                """)
            )
            stats: dict[str, dict[str, int]] = {}
            for row in result.fetchall():
                tier_key = f"tier_{row[0]}"
                if tier_key not in stats:
                    stats[tier_key] = {}
                stats[tier_key][str(row[1])] = int(row[2])
            return stats

    # =========================================================================
    # Human Reviews
    # =========================================================================

    def save_review(
        self,
        rule_id: str,
        reviewer_id: str,
        decision: str,
        notes: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ReviewRecord:
        record = ReviewRecord(
            rule_id=rule_id,
            reviewer_id=reviewer_id,
            decision=decision,
            notes=notes,
            metadata=metadata,
        )
        with get_db() as conn:
            conn.execute(
                text("""
                INSERT INTO reviews (
                    id, rule_id, reviewer_id, decision, notes, created_at, metadata
                ) VALUES (:id, :rule_id, :reviewer_id, :decision, :notes, :created_at, :metadata)
                """),
                {
                    "id": record.id,
                    "rule_id": record.rule_id,
                    "reviewer_id": record.reviewer_id,
                    "decision": record.decision,
                    "notes": record.notes,
                    "created_at": record.created_at,
                    "metadata": json.dumps(record.metadata) if record.metadata else None,
                },
            )
            conn.commit()
        return record

    def get_reviews_for_rule(self, rule_id: str) -> list[ReviewRecord]:
        with get_db() as conn:
            result = conn.execute(
                text("SELECT * FROM reviews WHERE rule_id = :rule_id ORDER BY created_at DESC"),
                {"rule_id": rule_id},
            )
            return [ReviewRecord.from_row(dict(row._mapping)) for row in result.fetchall()]

    def get_latest_review(self, rule_id: str) -> ReviewRecord | None:
        with get_db() as conn:
            result = conn.execute(
                text("""
                SELECT * FROM reviews WHERE rule_id = :rule_id
                ORDER BY created_at DESC LIMIT 1
                """),
                {"rule_id": rule_id},
            )
            row = result.fetchone()
            return ReviewRecord.from_row(dict(row._mapping)) if row else None

    def clear_all_verifications(self) -> int:
        with get_db() as conn:
            result = conn.execute(text("SELECT COUNT(*) as count FROM verification_results"))
            row = result.fetchone()
            count: int = int(row[0]) if row else 0
            conn.execute(text("DELETE FROM verification_evidence"))
            conn.execute(text("DELETE FROM verification_results"))
            conn.commit()
            return count

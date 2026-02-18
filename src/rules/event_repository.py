"""Rule event repository for event sourcing operations."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from src.database import get_db
from src.rules.models import RuleEventRecord, RuleEventType


class RuleEventRepository:
    """Repository for rule event persistence operations.

    Events are append-only and form an audit log of all rule changes.
    """

    def append_event(
        self,
        rule_id: str,
        version: int,
        event_type: str | RuleEventType,
        event_data: dict[str, Any],
        actor: str | None = None,
        reason: str | None = None,
    ) -> RuleEventRecord:
        """Append a new event to the event log."""
        if isinstance(event_type, RuleEventType):
            event_type = event_type.value

        sequence_number = self.get_next_sequence_number()
        event_data_json = json.dumps(event_data)

        record = RuleEventRecord(
            rule_id=rule_id,
            version=version,
            event_type=event_type,
            event_data=event_data_json,
            sequence_number=sequence_number,
            actor=actor,
            reason=reason,
        )

        with get_db() as conn:
            conn.execute(
                text("""
                INSERT INTO rule_events (
                    id, sequence_number, rule_id, version,
                    event_type, event_data, timestamp, actor, reason
                ) VALUES (:id, :sequence_number, :rule_id, :version,
                          :event_type, :event_data, :timestamp, :actor, :reason)
                """),
                {
                    "id": record.id,
                    "sequence_number": record.sequence_number,
                    "rule_id": record.rule_id,
                    "version": record.version,
                    "event_type": record.event_type,
                    "event_data": record.event_data,
                    "timestamp": record.timestamp,
                    "actor": record.actor,
                    "reason": record.reason,
                },
            )
            conn.commit()

        return record

    def get_events_for_rule(self, rule_id: str, limit: int | None = None) -> list[RuleEventRecord]:
        """Get all events for a rule."""
        with get_db() as conn:
            if limit:
                result = conn.execute(
                    text("""
                    SELECT * FROM rule_events
                    WHERE rule_id = :rule_id
                    ORDER BY sequence_number DESC
                    LIMIT :limit
                    """),
                    {"rule_id": rule_id, "limit": limit},
                )
            else:
                result = conn.execute(
                    text("""
                    SELECT * FROM rule_events
                    WHERE rule_id = :rule_id
                    ORDER BY sequence_number DESC
                    """),
                    {"rule_id": rule_id},
                )
            return [RuleEventRecord.from_row(row._mapping) for row in result.fetchall()]

    def get_events_by_type(self, event_type: str | RuleEventType, limit: int = 100) -> list[RuleEventRecord]:
        """Get all events of a specific type."""
        if isinstance(event_type, RuleEventType):
            event_type = event_type.value

        with get_db() as conn:
            result = conn.execute(
                text("""
                SELECT * FROM rule_events
                WHERE event_type = :event_type
                ORDER BY sequence_number DESC
                LIMIT :limit
                """),
                {"event_type": event_type, "limit": limit},
            )
            return [RuleEventRecord.from_row(row._mapping) for row in result.fetchall()]

    def get_events_after_sequence(self, sequence_number: int, limit: int = 100) -> list[RuleEventRecord]:
        """Get all events after a specific sequence number."""
        with get_db() as conn:
            result = conn.execute(
                text("""
                SELECT * FROM rule_events
                WHERE sequence_number > :sequence_number
                ORDER BY sequence_number ASC
                LIMIT :limit
                """),
                {"sequence_number": sequence_number, "limit": limit},
            )
            return [RuleEventRecord.from_row(row._mapping) for row in result.fetchall()]

    def get_next_sequence_number(self) -> int:
        """Get the next sequence number for events."""
        with get_db() as conn:
            result = conn.execute(text("SELECT MAX(sequence_number) as max_seq FROM rule_events"))
            row = result.fetchone()
            return (row[0] or 0) + 1

    def get_latest_event(self, rule_id: str) -> RuleEventRecord | None:
        """Get the most recent event for a rule."""
        with get_db() as conn:
            result = conn.execute(
                text("""
                SELECT * FROM rule_events
                WHERE rule_id = :rule_id
                ORDER BY sequence_number DESC
                LIMIT 1
                """),
                {"rule_id": rule_id},
            )
            row = result.fetchone()
            if row:
                return RuleEventRecord.from_row(row._mapping)
            return None

    def count_events(self, rule_id: str | None = None) -> int:
        """Count events."""
        with get_db() as conn:
            if rule_id:
                result = conn.execute(
                    text("SELECT COUNT(*) as count FROM rule_events WHERE rule_id = :rule_id"),
                    {"rule_id": rule_id},
                )
            else:
                result = conn.execute(text("SELECT COUNT(*) as count FROM rule_events"))
            return result.fetchone()[0]

    def get_event_summary(self) -> dict[str, int]:
        """Get a summary of events by type."""
        with get_db() as conn:
            result = conn.execute(
                text("""
                SELECT event_type, COUNT(*) as count
                FROM rule_events
                GROUP BY event_type
                ORDER BY event_type
                """)
            )
            return {row[0]: row[1] for row in result.fetchall()}

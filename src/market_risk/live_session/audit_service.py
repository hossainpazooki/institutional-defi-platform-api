"""Audit replay — chronological join over the 4 live-session hypertables.

See spec §8.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlmodel import select

from .models import NLICheckRow, RationaleRow, ThresholdEventRow, TradeSnapshotRow

if TYPE_CHECKING:
    from sqlmodel import Session


@dataclass
class AuditRecord:
    table: str
    row: dict[str, Any]
    ts: str  # ISO 8601


def fetch_audit(session: Session, intent_id: str) -> list[AuditRecord]:
    """Return chronological events for an intent.

    Joins are by intent_id; ordering by ts. Replay-fidelity preserves the
    original `ts` rather than rewriting to "now" (see spec §8 risk note).
    """
    snapshots = list(
        session.exec(
            select(TradeSnapshotRow).where(TradeSnapshotRow.intent_id == intent_id)
        )
    )
    events = list(
        session.exec(
            select(ThresholdEventRow).where(ThresholdEventRow.intent_id == intent_id)
        )
    )
    rationales = list(
        session.exec(
            select(RationaleRow).where(RationaleRow.intent_id == intent_id)
        )
    )
    nli = list(
        session.exec(select(NLICheckRow).where(NLICheckRow.intent_id == intent_id))
    )

    records: list[AuditRecord] = []
    for snap in snapshots:
        records.append(
            AuditRecord(table="trade_snapshots", row=snap.model_dump(mode="json"), ts=snap.ts.isoformat())
        )
    for ev in events:
        records.append(
            AuditRecord(table="threshold_events", row=ev.model_dump(mode="json"), ts=ev.ts.isoformat())
        )
    for rat in rationales:
        records.append(
            AuditRecord(table="rationales", row=rat.model_dump(mode="json"), ts=rat.ts.isoformat())
        )
    for chk in nli:
        records.append(
            AuditRecord(table="nli_checks", row=chk.model_dump(mode="json"), ts=chk.ts.isoformat())
        )

    records.sort(key=lambda x: x.ts)
    return records


__all__ = ["AuditRecord", "fetch_audit"]

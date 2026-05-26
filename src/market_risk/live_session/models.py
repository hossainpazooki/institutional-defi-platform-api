"""SQLModel ORM tables for live-session persistence.

4 hypertables on TimescaleDB: trade_snapshots (1Hz audit cadence), threshold_events,
rationales, nli_checks. Retention 90d default (per unified-plan decision 1).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlmodel import Column, DateTime, Field, SQLModel

if TYPE_CHECKING:
    from datetime import datetime
    from decimal import Decimal


class TradeSnapshotRow(SQLModel, table=True):
    """Persisted snapshot — attached-only + audit-cadence (1Hz) sample."""

    __tablename__ = "trade_snapshots"

    id: int | None = Field(default=None, primary_key=True)
    intent_id: str = Field(index=True)
    ts: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True)
    )
    mark_price: Decimal
    bid: Decimal
    ask: Decimal
    size: Decimal
    spread_bps: float
    slippage_bps: float
    vol_30d: float
    var_95_usd: float
    funding_rate: float | None = None


class ThresholdEventRow(SQLModel, table=True):
    __tablename__ = "threshold_events"

    id: int | None = Field(default=None, primary_key=True)
    crossing_id: str = Field(index=True, unique=True)
    intent_id: str = Field(index=True)
    ts: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True)
    )
    rule_id: str = Field(index=True)
    citation: str
    boundary: Decimal
    direction: str  # crossed_up | crossed_down
    prior_verdict: str
    new_verdict: str
    compliance_critical: bool = False


class RationaleRow(SQLModel, table=True):
    __tablename__ = "rationales"

    id: int | None = Field(default=None, primary_key=True)
    rationale_id: str = Field(index=True, unique=True)
    crossing_id: str = Field(index=True)
    intent_id: str = Field(index=True)
    ts: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True)
    )
    content: str
    status: str  # streaming | verified | retracted
    final_score: float | None = None
    retraction_reason: str | None = None
    completed_at: datetime | None = None


class NLICheckRow(SQLModel, table=True):
    __tablename__ = "nli_checks"

    id: int | None = Field(default=None, primary_key=True)
    nli_check_id: str = Field(index=True, unique=True)
    rationale_id: str = Field(index=True)
    intent_id: str = Field(index=True)
    ts: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True)
    )
    token_offset: int
    entailment_score: float


__all__ = [
    "NLICheckRow",
    "RationaleRow",
    "ThresholdEventRow",
    "TradeSnapshotRow",
]

"""SQLModel ORM tables for live-session persistence.

4 hypertables on TimescaleDB: trade_snapshots (1Hz audit cadence), threshold_events,
rationales, nli_checks. Retention 90d default (per unified-plan decision 1).

1 regular table: trade_intents — the canonical record of a session's intent.
Created via REST (POST /v2/intents), read by the session registry resolver.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON
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


class TradeIntentRow(SQLModel, table=True):
    """Canonical persisted trade intent — created via POST /v2/intents."""

    __tablename__ = "trade_intents"

    intent_id: str = Field(primary_key=True)
    asset: str = Field(index=True)
    direction: str  # buy | sell
    notional_usd: Decimal
    venue_jurisdiction: str
    investor_type: str  # retail | professional | eligible_counterparty
    target_jurisdictions: list[str] = Field(
        sa_column=Column(JSON, nullable=False)
    )
    holding_period_days: int
    status: str = Field(default="created", index=True)  # created | active | closed | failed
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True)
    )
    activated_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    closed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    last_error: str | None = Field(default=None, nullable=True)


__all__ = [
    "NLICheckRow",
    "RationaleRow",
    "ThresholdEventRow",
    "TradeIntentRow",
    "TradeSnapshotRow",
]

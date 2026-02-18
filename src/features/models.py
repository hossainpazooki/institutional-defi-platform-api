"""SQLModel models for Feature Store domain."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Column, Field, SQLModel


class RiskFeature(SQLModel, table=True):
    """Risk Feature Store model — designed for TimescaleDB hypertable.

    Stores all computed risk metrics with timestamps and provenance.
    """

    __tablename__ = "risk_features"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    asset_or_protocol_id: str = Field(index=True, max_length=255)
    feature_name: str = Field(index=True, max_length=255)
    value: dict[str, Any] = Field(sa_column=Column(JSONB, nullable=False))
    ts: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC),
        primary_key=True,
    )
    source: str = Field(max_length=100)
    confidence: float | None = Field(default=None, ge=0, le=1)
    metadata_: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column("metadata", JSONB),
    )

    __table_args__ = (
        Index(
            "idx_risk_features_lookup",
            "asset_or_protocol_id",
            "feature_name",
            "ts",
        ),
        Index("idx_risk_features_entity", "asset_or_protocol_id", "ts"),
        Index("idx_risk_features_source", "source", "ts"),
    )

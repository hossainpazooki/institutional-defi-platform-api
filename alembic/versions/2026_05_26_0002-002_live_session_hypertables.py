"""live session hypertables

Revision ID: 002
Revises: 001
Create Date: 2026-05-26

Creates 4 hypertables for the live trading session pipeline:
- trade_snapshots (1Hz audit cadence)
- threshold_events
- rationales
- nli_checks

Each is partitioned on `ts` with 7-day chunks; 90-day retention policy.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa

from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence


revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_hypertable_safe(table: str) -> None:
    """Create a hypertable; no-op if TimescaleDB extension is absent (e.g. SQLite test DB)."""
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
            PERFORM create_hypertable('{table}', 'ts',
                                     chunk_time_interval => INTERVAL '7 days',
                                     if_not_exists => TRUE);
            PERFORM add_retention_policy('{table}', INTERVAL '90 days',
                                         if_not_exists => TRUE);
          END IF;
        END
        $$;
        """
    )


def upgrade() -> None:
    op.create_table(
        "trade_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("intent_id", sa.String(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mark_price", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("bid", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("ask", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("size", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("spread_bps", sa.Float(), nullable=False),
        sa.Column("slippage_bps", sa.Float(), nullable=False),
        sa.Column("vol_30d", sa.Float(), nullable=False),
        sa.Column("var_95_usd", sa.Float(), nullable=False),
        sa.Column("funding_rate", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trade_snapshots")),
    )
    op.create_index("ix_trade_snapshots_intent_id", "trade_snapshots", ["intent_id"])
    op.create_index("ix_trade_snapshots_ts", "trade_snapshots", ["ts"])

    op.create_table(
        "threshold_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("crossing_id", sa.String(), nullable=False),
        sa.Column("intent_id", sa.String(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rule_id", sa.String(), nullable=False),
        sa.Column("citation", sa.String(), nullable=False),
        sa.Column("boundary", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("direction", sa.String(), nullable=False),
        sa.Column("prior_verdict", sa.String(), nullable=False),
        sa.Column("new_verdict", sa.String(), nullable=False),
        sa.Column("compliance_critical", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_threshold_events")),
        sa.UniqueConstraint("crossing_id", name=op.f("uq_threshold_events_crossing_id")),
    )
    op.create_index("ix_threshold_events_intent_id", "threshold_events", ["intent_id"])
    op.create_index("ix_threshold_events_ts", "threshold_events", ["ts"])
    op.create_index("ix_threshold_events_rule_id", "threshold_events", ["rule_id"])

    op.create_table(
        "rationales",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("rationale_id", sa.String(), nullable=False),
        sa.Column("crossing_id", sa.String(), nullable=False),
        sa.Column("intent_id", sa.String(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("final_score", sa.Float(), nullable=True),
        sa.Column("retraction_reason", sa.String(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rationales")),
        sa.UniqueConstraint("rationale_id", name=op.f("uq_rationales_rationale_id")),
    )
    op.create_index("ix_rationales_crossing_id", "rationales", ["crossing_id"])
    op.create_index("ix_rationales_intent_id", "rationales", ["intent_id"])
    op.create_index("ix_rationales_ts", "rationales", ["ts"])

    op.create_table(
        "nli_checks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("nli_check_id", sa.String(), nullable=False),
        sa.Column("rationale_id", sa.String(), nullable=False),
        sa.Column("intent_id", sa.String(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("token_offset", sa.Integer(), nullable=False),
        sa.Column("entailment_score", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_nli_checks")),
        sa.UniqueConstraint("nli_check_id", name=op.f("uq_nli_checks_nli_check_id")),
    )
    op.create_index("ix_nli_checks_rationale_id", "nli_checks", ["rationale_id"])
    op.create_index("ix_nli_checks_intent_id", "nli_checks", ["intent_id"])
    op.create_index("ix_nli_checks_ts", "nli_checks", ["ts"])

    # Convert to hypertables + retention (no-op if Timescale extension absent).
    for tbl in ("trade_snapshots", "threshold_events", "rationales", "nli_checks"):
        _create_hypertable_safe(tbl)


def downgrade() -> None:
    op.drop_table("nli_checks")
    op.drop_table("rationales")
    op.drop_table("threshold_events")
    op.drop_table("trade_snapshots")

"""trade intents table

Revision ID: 003
Revises: 002
Create Date: 2026-05-27

Creates the `trade_intents` table — canonical record of a live-session intent.
Not a hypertable: intents are low-cardinality session-defining rows; ts queries
are on the related event tables (threshold_events, rationales, nli_checks).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa

from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence


revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trade_intents",
        sa.Column("intent_id", sa.String(), nullable=False),
        sa.Column("asset", sa.String(), nullable=False),
        sa.Column("direction", sa.String(), nullable=False),
        sa.Column("notional_usd", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("venue_jurisdiction", sa.String(), nullable=False),
        sa.Column("investor_type", sa.String(), nullable=False),
        sa.Column("target_jurisdictions", sa.JSON(), nullable=False),
        sa.Column("holding_period_days", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'created'"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("intent_id", name=op.f("pk_trade_intents")),
    )
    op.create_index("ix_trade_intents_asset", "trade_intents", ["asset"])
    op.create_index("ix_trade_intents_status", "trade_intents", ["status"])
    op.create_index("ix_trade_intents_created_at", "trade_intents", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_trade_intents_created_at", table_name="trade_intents")
    op.drop_index("ix_trade_intents_status", table_name="trade_intents")
    op.drop_index("ix_trade_intents_asset", table_name="trade_intents")
    op.drop_table("trade_intents")

"""trade intent lifecycle columns

Revision ID: 004
Revises: 003
Create Date: 2026-05-28

Adds lifecycle metadata to `trade_intents`:
- `activated_at` (nullable timestamptz) — stamped on first registry acquire
- `closed_at` (nullable timestamptz) — stamped on final release
- `last_error` (nullable text) — populated when status flips to `failed`

All columns are nullable; existing rows (status='created') get NULL.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa

from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence


revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "trade_intents",
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "trade_intents",
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "trade_intents",
        sa.Column("last_error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("trade_intents", "last_error")
    op.drop_column("trade_intents", "closed_at")
    op.drop_column("trade_intents", "activated_at")

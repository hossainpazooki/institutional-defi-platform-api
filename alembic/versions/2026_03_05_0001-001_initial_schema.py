"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-03-05

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── embedding_rules (parent table) ───────────────────────────────
    op.create_table(
        "embedding_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("rule_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_embedding_rules")),
        sa.UniqueConstraint("rule_id", name=op.f("uq_embedding_rules_rule_id")),
    )
    op.create_index("ix_embedding_rules_rule_id", "embedding_rules", ["rule_id"])

    # ── rule_embeddings ──────────────────────────────────────────────
    op.create_table(
        "rule_embeddings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("rule_id", sa.Integer(), nullable=False),
        sa.Column("embedding_type", sa.String(), nullable=False),
        sa.Column("vector_json", sa.String(), nullable=False),
        sa.Column("embedding_vector", sa.LargeBinary(), nullable=True),
        sa.Column("vector_dim", sa.Integer(), nullable=False),
        sa.Column("model_name", sa.String(), nullable=False),
        sa.Column("source_text", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rule_embeddings")),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["embedding_rules.id"],
            name=op.f("fk_rule_embeddings_rule_id_embedding_rules"),
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_rule_embeddings_rule_id", "rule_embeddings", ["rule_id"])
    op.create_index("ix_rule_embeddings_embedding_type", "rule_embeddings", ["embedding_type"])

    # ── graph_embeddings ─────────────────────────────────────────────
    op.create_table(
        "graph_embeddings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("rule_id", sa.Integer(), nullable=False),
        sa.Column("embedding_vector", sa.LargeBinary(), nullable=False),
        sa.Column("vector_json", sa.String(), nullable=True),
        sa.Column("vector_dim", sa.Integer(), nullable=False),
        sa.Column("graph_json", sa.String(), nullable=False),
        sa.Column("num_nodes", sa.Integer(), nullable=False),
        sa.Column("num_edges", sa.Integer(), nullable=False),
        sa.Column("model_name", sa.String(), nullable=False),
        sa.Column("walk_length", sa.Integer(), nullable=False),
        sa.Column("num_walks", sa.Integer(), nullable=False),
        sa.Column("p", sa.Float(), nullable=False),
        sa.Column("q", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_graph_embeddings")),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["embedding_rules.id"],
            name=op.f("fk_graph_embeddings_rule_id_embedding_rules"),
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_graph_embeddings_rule_id", "graph_embeddings", ["rule_id"])

    # ── embedding_conditions ─────────────────────────────────────────
    op.create_table(
        "embedding_conditions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("field", sa.String(), nullable=False),
        sa.Column("operator", sa.String(), nullable=False),
        sa.Column("value", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("rule_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_embedding_conditions")),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["embedding_rules.id"],
            name=op.f("fk_embedding_conditions_rule_id_embedding_rules"),
            ondelete="CASCADE",
        ),
    )

    # ── embedding_decisions ──────────────────────────────────────────
    op.create_table(
        "embedding_decisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("explanation", sa.String(), nullable=True),
        sa.Column("rule_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_embedding_decisions")),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["embedding_rules.id"],
            name=op.f("fk_embedding_decisions_rule_id_embedding_rules"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("rule_id", name=op.f("uq_embedding_decisions_rule_id")),
    )

    # ── embedding_legal_sources ──────────────────────────────────────
    op.create_table(
        "embedding_legal_sources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("citation", sa.String(), nullable=False),
        sa.Column("document_id", sa.String(), nullable=True),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("rule_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_embedding_legal_sources")),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["embedding_rules.id"],
            name=op.f("fk_embedding_legal_sources_rule_id_embedding_rules"),
            ondelete="CASCADE",
        ),
    )

    # ── risk_features (TimescaleDB hypertable candidate) ─────────────
    op.create_table(
        "risk_features",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_or_protocol_id", sa.String(length=255), nullable=False),
        sa.Column("feature_name", sa.String(length=255), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("id", "ts", name=op.f("pk_risk_features")),
    )
    op.create_index("ix_risk_features_asset_or_protocol_id", "risk_features", ["asset_or_protocol_id"])
    op.create_index("ix_risk_features_feature_name", "risk_features", ["feature_name"])
    op.create_index(
        "idx_risk_features_lookup",
        "risk_features",
        ["asset_or_protocol_id", "feature_name", "ts"],
    )
    op.create_index(
        "idx_risk_features_entity",
        "risk_features",
        ["asset_or_protocol_id", "ts"],
    )
    op.create_index(
        "idx_risk_features_source",
        "risk_features",
        ["source", "ts"],
    )


def downgrade() -> None:
    op.drop_table("risk_features")
    op.drop_table("embedding_legal_sources")
    op.drop_table("embedding_decisions")
    op.drop_table("embedding_conditions")
    op.drop_table("graph_embeddings")
    op.drop_table("rule_embeddings")
    op.drop_table("embedding_rules")

"""Alembic migration environment configuration.

Imports all SQLModel table models so their metadata is registered,
then uses SQLModel.metadata as the migration target.
"""

from __future__ import annotations

import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

# ── Import all SQLModel table models ──────────────────────────────────
# These imports register tables on SQLModel.metadata so autogenerate
# can detect them.  Only modules with `SQLModel, table=True` classes
# need to be listed here.
from src.embeddings.models import (  # noqa: F401
    EmbeddingCondition,
    EmbeddingDecision,
    EmbeddingLegalSource,
    EmbeddingRule,
    GraphEmbedding,
    RuleEmbedding,
)
from src.features.models import RiskFeature  # noqa: F401

# Apply the naming convention from src.database (ensures Alembic uses
# the same constraint names as the application).
from src.database import convention

SQLModel.metadata.naming_convention = convention

# ── Alembic config ────────────────────────────────────────────────────
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

target_metadata = SQLModel.metadata


def get_url() -> str:
    """Resolve database URL from application settings, with alembic.ini fallback."""
    try:
        from src.config import get_settings

        settings = get_settings()
        url = settings.database_url
        # Railway postgres:// → postgresql:// normalization
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url
    except Exception:
        # Fall back to alembic.ini sqlalchemy.url
        return config.get_main_option("sqlalchemy.url", "")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Generates SQL script without connecting to the database.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Creates an engine and connects to the database.
    """
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

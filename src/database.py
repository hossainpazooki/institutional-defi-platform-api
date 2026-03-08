"""Database connection management for PostgreSQL + TimescaleDB.

Merges patterns from:
- Workbench core/database.py: SQLModel sessions, engine creation
- Workbench storage/database.py: raw connection management
- Console database.py: connection pooling, TimescaleDB hypertable init

Design decisions:
- PostgreSQL-only (no SQLite fallback; use docker-compose for local dev)
- Connection pooling: pool_size=5, max_overflow=10, pool_pre_ping=True
- Alembic-aware: no auto-create_all; tables managed via migrations
- Explicit index naming convention via SQLAlchemy MetaData
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Connection, Engine, MetaData, text
from sqlmodel import Session, SQLModel, create_engine

from src.config import get_settings

# Explicit naming convention for constraints and indexes (Alembic best practice)
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=convention)

# Apply naming convention to SQLModel's default metadata
SQLModel.metadata.naming_convention = convention

_engine: Engine | None = None


def _normalize_url(url: str) -> str:
    """Normalize database URL for SQLAlchemy compatibility.

    Handles Railway's postgres:// → postgresql:// conversion.
    """
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


def get_engine() -> Engine:
    """Get SQLAlchemy engine with connection pooling.

    Engine is created lazily and cached as a module-level singleton.
    """
    global _engine
    if _engine is None:
        settings = get_settings()
        database_url = _normalize_url(settings.database_url)
        _engine = create_engine(
            database_url,
            echo=settings.debug,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
    return _engine


def reset_engine() -> None:
    """Reset the engine singleton (for testing or reconfiguration)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def get_session() -> Iterator[Session]:
    """Yield a SQLModel session for FastAPI dependency injection."""
    with Session(get_engine()) as session:
        yield session


@contextmanager
def get_db() -> Iterator[Connection]:
    """Get a raw SQLAlchemy connection via context manager.

    Used by repository classes for direct SQL operations::

        with get_db() as conn:
            result = conn.execute(text("SELECT * FROM rules"))
    """
    engine = get_engine()
    with engine.connect() as conn:
        yield conn


def init_timescaledb_hypertable(table_name: str, time_column: str = "ts") -> None:
    """Initialize a TimescaleDB hypertable for time-series data.

    Safe to call multiple times; skips if already a hypertable or if
    TimescaleDB is not installed.
    """
    engine = get_engine()
    try:
        with engine.connect() as conn:
            # Check if table exists
            result = conn.execute(
                text("SELECT EXISTS (  SELECT FROM information_schema.tables  WHERE table_name = :table_name)"),
                {"table_name": table_name},
            )
            if not result.scalar():
                return

            # Check if already a hypertable
            result = conn.execute(
                text(
                    "SELECT EXISTS ("
                    "  SELECT FROM timescaledb_information.hypertables"
                    "  WHERE hypertable_name = :table_name"
                    ")"
                ),
                {"table_name": table_name},
            )
            if result.scalar():
                return

            conn.execute(
                text(
                    "SELECT create_hypertable(:table_name, :time_column, if_not_exists => TRUE, migrate_data => TRUE)"
                ),
                {"table_name": table_name, "time_column": time_column},
            )
            conn.commit()
    except Exception:
        # TimescaleDB extension may not be available in all environments
        pass

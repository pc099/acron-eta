"""
Database engine and session factory for PostgreSQL.

Used when DATABASE_URL is set. Creates tables on init if they do not exist.
"""

import logging
from typing import TYPE_CHECKING

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all models."""

    pass


def get_engine(database_url: str, pool_size: int = 10) -> "Engine":
    """Create a SQLAlchemy engine for the given database URL.

    Args:
        database_url: PostgreSQL connection URL (e.g. from DATABASE_URL).
        pool_size: Connection pool size.

    Returns:
        SQLAlchemy Engine instance.
    """
    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=pool_size,
        echo=False,
    )


def get_session_factory(engine: "Engine") -> sessionmaker[Session]:
    """Create a session factory bound to the engine.

    Args:
        engine: SQLAlchemy engine.

    Returns:
        Session factory (call to get a new Session).
    """
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db(engine: "Engine") -> None:
    """Create all tables if they do not exist.

    Idempotent: safe to call on every startup.

    Args:
        engine: SQLAlchemy engine.
    """
    from src.db.models import ApiKeyModel, OrgModel  # noqa: F401

    Base.metadata.create_all(bind=engine)
    logger.info("Database tables ensured", extra={})

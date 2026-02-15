"""
Database engine and session factory for PostgreSQL.

Used when DATABASE_URL is set. Creates tables on init if they do not exist.
Supports both sync (Session) and async (AsyncSession) for auth routes.
"""

import logging
from typing import TYPE_CHECKING, AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# Async engine/session for auth router (set by init_async_engine)
_async_engine = None
_async_session_factory = None


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
    from src.db.models import ApiKeyModel, OrgModel, UserModel  # noqa: F401

    Base.metadata.create_all(bind=engine)
    logger.info("Database tables ensured", extra={})


def init_async_engine(database_url: str, pool_size: int = 10) -> None:
    """Create async engine and session factory for FastAPI auth routes.

    Call once at app startup when DATABASE_URL is set.
    Use postgresql+asyncpg:// URL scheme.
    """
    global _async_engine, _async_session_factory
    try:
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    except ImportError as e:
        raise ImportError("Async DB requires sqlalchemy[asyncio] and asyncpg") from e
    url = database_url
    if url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[11:]
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    _async_engine = create_async_engine(
        url,
        pool_pre_ping=True,
        pool_size=pool_size,
        echo=False,
    )
    _async_session_factory = async_sessionmaker(
        bind=_async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    logger.info("Async DB engine initialised", extra={})


async def get_async_session() -> AsyncGenerator["AsyncSession", None]:
    """FastAPI dependency that yields an async session. Requires init_async_engine() at startup."""
    if _async_session_factory is None:
        raise RuntimeError("Async DB not initialised; call init_async_engine() when DATABASE_URL is set")
    from sqlalchemy.ext.asyncio import AsyncSession
    async with _async_session_factory() as session:
        yield session

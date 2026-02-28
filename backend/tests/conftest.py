"""Test fixtures for ASAHI backend.

Sets up an in-memory SQLite database, overrides the async engine and
session factory, and provides a FastAPI app and AsyncClient for tests.
"""

import asyncio
import os
import uuid as _uuid
from collections.abc import AsyncGenerator
from typing import Any, AsyncIterator

import pytest
from httpx import AsyncClient
from sqlalchemy import JSON, String, event
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Register SQLite type adapters for PostgreSQL-specific column types.
# This lets the same ORM models work with both PostgreSQL (production)
# and SQLite (tests) without changing model definitions.
from sqlalchemy import TypeDecorator


class _JSONBtoJSON(TypeDecorator):
    """Render JSONB as plain JSON for SQLite."""
    impl = JSON
    cache_ok = True


class _UUIDtoString(TypeDecorator):
    """Render PostgreSQL UUID as CHAR(36) for SQLite."""
    impl = String(36)
    cache_ok = True


# Monkey-patch the dialect adapters before any model metadata is compiled
import sqlalchemy.dialects.sqlite.base as sqlite_dialect  # noqa: E402

_orig_get_colspec = sqlite_dialect.SQLiteTypeCompiler.visit_JSONB if hasattr(sqlite_dialect.SQLiteTypeCompiler, 'visit_JSONB') else None

# Add JSONB and UUID support to SQLite type compiler
sqlite_dialect.SQLiteTypeCompiler.visit_JSONB = lambda self, type_, **kw: "JSON"
sqlite_dialect.SQLiteTypeCompiler.visit_UUID = lambda self, type_, **kw: "CHAR(36)"

# Ensure tests use SQLite instead of a real PostgreSQL instance
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")
os.environ.setdefault("DEBUG", "true")

from app.main import create_app  # noqa: E402
from app.db import engine as db_engine  # noqa: E402
from app.db.models import AuditLog, ApiKey, Base, KeyEnvironment, Member, MemberRole, Organisation, User  # noqa: E402


@pytest.fixture(scope="session")
def event_loop() -> AsyncIterator[asyncio.AbstractEventLoop]:
  """Create a session-scoped event loop for async tests."""
  loop = asyncio.new_event_loop()
  try:
      yield loop
  finally:
      loop.close()


@pytest.fixture(scope="session")
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    """Session-scoped async SQLite engine with all tables created."""
    test_engine = create_async_engine(
        os.environ["DATABASE_URL"],
        future=True,
    )
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield test_engine
    await test_engine.dispose()


@pytest.fixture(scope="session")
async def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Session factory bound to the test engine."""
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest.fixture(scope="session", autouse=True)
def override_db_engine(engine: AsyncEngine, session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Override global engine and async_session_factory used by app code."""
    db_engine.engine = engine
    db_engine.async_session_factory = session_factory


@pytest.fixture
async def app() -> Any:
    """FastAPI application instance for tests."""
    app = create_app()
    # Disable Redis for tests; rate limit middleware will log a warning but allow requests.
    app.state.redis = None
    return app


@pytest.fixture
async def client(app: Any) -> AsyncGenerator[AsyncClient, None]:
    """HTTPX AsyncClient bound to the FastAPI app."""
    async with AsyncClient(app=app, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
async def seed_org(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    """Create a test organisation, user, membership, and API key."""
    async with session_factory() as session:
        suffix = _uuid.uuid4().hex[:8]
        user = User(email=f"test-{suffix}@example.com", name="Test User")
        session.add(user)
        await session.flush()

        org = Organisation(name="Test Org", slug=f"test-org-{suffix}")
        session.add(org)
        await session.flush()

        member = Member(
            organisation_id=org.id,
            user_id=user.id,
            role=MemberRole.OWNER,
        )
        session.add(member)

        raw_key, prefix, key_hash, last_four = ApiKey.generate(environment="live")
        api_key = ApiKey(
            organisation_id=org.id,
            created_by_user_id=user.id,
            name="Test Key",
            environment=KeyEnvironment.LIVE,
            prefix=prefix,
            key_hash=key_hash,
            last_four=last_four,
            scopes=["*"],
            is_active=True,
        )
        session.add(api_key)
        await session.commit()

        return {
            "user": user,
            "org": org,
            "member": member,
            "api_key": api_key,
            "raw_key": raw_key,
        }

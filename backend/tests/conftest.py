"""Test fixtures for ASAHI backend.

Sets up an in-memory SQLite database, overrides the async engine and
session factory, and provides a FastAPI app and AsyncClient for tests.
"""

import asyncio
import os
from collections.abc import AsyncGenerator
from typing import Any, AsyncIterator

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Ensure tests use SQLite instead of a real PostgreSQL instance
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")
os.environ.setdefault("DEBUG", "true")

from app.main import create_app  # noqa: E402
from app.db import engine as db_engine  # noqa: E402
from app.db.models import ApiKey, KeyEnvironment, Member, MemberRole, Organisation, User  # noqa: E402


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
        await conn.run_sync(Organisation.metadata.bind.metadata.create_all)  # type: ignore[attr-defined]
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
        user = User(email="test@example.com", name="Test User")
        session.add(user)
        await session.flush()

        org = Organisation(name="Test Org", slug="test-org")
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


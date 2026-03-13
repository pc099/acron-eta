"""Tests for the audit middleware."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import AuditLog


def _auth_header(raw_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {raw_key}"}


async def test_audit_logs_authenticated_request(
    client: AsyncClient,
    seed_org: dict,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Authenticated requests should generate audit log entries."""
    raw_key = seed_org["raw_key"]
    org = seed_org["org"]

    # Make an authenticated request
    resp = await client.get("/agents", headers=_auth_header(raw_key))
    assert resp.status_code == 200

    # Give the background task time to complete
    import asyncio
    await asyncio.sleep(0.2)

    # Check audit log
    async with session_factory() as session:
        result = await session.execute(
            select(AuditLog)
            .where(AuditLog.organisation_id == org.id)
            .order_by(AuditLog.created_at.desc())
        )
        logs = result.scalars().all()
        # Should have at least one audit entry for GET /agents
        agent_logs = [l for l in logs if "GET /agents" in l.action]
        assert len(agent_logs) >= 1

        log = agent_logs[0]
        assert log.resource_type == "http_request"
        assert log.metadata_.get("auth_type") == "api_key"


async def test_audit_skips_health_endpoint(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Health endpoint should not generate audit log entries."""
    resp = await client.get("/health")
    assert resp.status_code == 200

    # Give the background task time
    import asyncio
    await asyncio.sleep(0.2)

    async with session_factory() as session:
        result = await session.execute(
            select(AuditLog).where(AuditLog.action == "GET /health")
        )
        logs = result.scalars().all()
        assert len(logs) == 0


async def test_audit_skips_unauthenticated_request(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Unauthenticated requests should not generate audit log entries."""
    # Request without auth header (will get 401)
    resp = await client.get("/agents")
    assert resp.status_code == 401

    import asyncio
    await asyncio.sleep(0.2)

    async with session_factory() as session:
        result = await session.execute(
            select(AuditLog).where(AuditLog.action == "GET /agents")
        )
        logs = result.scalars().all()
        # Only authenticated requests should be logged — if there are entries,
        # they should be from previous tests with auth
        unauthed = [l for l in logs if l.metadata_ and l.metadata_.get("auth_type") is None]
        assert len(unauthed) == 0

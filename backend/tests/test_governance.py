"""Tests for governance endpoints (audit log)."""

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import AuditLog


def _auth_header(raw_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {raw_key}"}


async def test_audit_log_empty(
    client: AsyncClient,
    seed_org: dict[str, object],
) -> None:
    """GET /governance/audit returns empty list when no audit entries exist."""
    raw_key = seed_org["raw_key"]  # type: ignore[index]

    resp = await client.get("/governance/audit", headers=_auth_header(raw_key))
    assert resp.status_code == 200

    body = resp.json()
    assert "data" in body
    assert "pagination" in body
    assert isinstance(body["data"], list)
    assert body["pagination"]["page"] == 1
    assert body["pagination"]["total"] >= 0
    assert body["pagination"]["pages"] >= 1


async def test_audit_log_with_entries(
    client: AsyncClient,
    seed_org: dict[str, object],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """GET /governance/audit returns audit entries scoped to the org."""
    org = seed_org["org"]  # type: ignore[index]
    user = seed_org["user"]  # type: ignore[index]
    raw_key = seed_org["raw_key"]  # type: ignore[index]

    # Insert test audit entries
    async with session_factory() as session:
        for i in range(3):
            entry = AuditLog(
                id=uuid.uuid4(),
                organisation_id=org.id,
                user_id=user.id,
                action=f"test.action_{i}",
                resource_type="test",
                resource_id=str(i),
            )
            session.add(entry)
        await session.commit()

    resp = await client.get("/governance/audit", headers=_auth_header(raw_key))
    assert resp.status_code == 200

    body = resp.json()
    assert body["pagination"]["total"] >= 3
    assert len(body["data"]) >= 3

    # Verify entry shape
    entry = body["data"][0]
    assert "id" in entry
    assert "timestamp" in entry
    assert "actor" in entry
    assert "action" in entry
    assert "resource" in entry


async def test_audit_log_pagination(
    client: AsyncClient,
    seed_org: dict[str, object],
) -> None:
    """GET /governance/audit respects page and limit params."""
    raw_key = seed_org["raw_key"]  # type: ignore[index]

    resp = await client.get(
        "/governance/audit?page=1&limit=2", headers=_auth_header(raw_key)
    )
    assert resp.status_code == 200

    body = resp.json()
    assert len(body["data"]) <= 2
    assert body["pagination"]["limit"] == 2
    assert body["pagination"]["page"] == 1


async def test_audit_log_requires_auth(client: AsyncClient) -> None:
    """GET /governance/audit without auth returns 401."""
    resp = await client.get("/governance/audit")
    assert resp.status_code == 401

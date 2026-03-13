"""Tests for agent lifecycle endpoints (archive, stats)."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Agent, AgentSession, CallTrace, InterventionMode, RoutingMode


def _auth_header(raw_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {raw_key}"}


async def test_archive_agent(
    client: AsyncClient,
    seed_org: dict,
) -> None:
    raw_key = seed_org["raw_key"]

    # Create an agent first
    create_resp = await client.post(
        "/agents",
        json={"name": "Archive Test Agent"},
        headers=_auth_header(raw_key),
    )
    assert create_resp.status_code == 201
    agent = create_resp.json()
    assert agent["is_active"] is True

    # Archive it
    archive_resp = await client.post(
        f"/agents/{agent['id']}/archive",
        headers=_auth_header(raw_key),
    )
    assert archive_resp.status_code == 200
    archived = archive_resp.json()
    assert archived["is_active"] is False


async def test_archive_nonexistent_agent(
    client: AsyncClient,
    seed_org: dict,
) -> None:
    raw_key = seed_org["raw_key"]
    fake_id = str(uuid.uuid4())
    resp = await client.post(
        f"/agents/{fake_id}/archive",
        headers=_auth_header(raw_key),
    )
    assert resp.status_code == 404


async def test_agent_stats_empty(
    client: AsyncClient,
    seed_org: dict,
) -> None:
    raw_key = seed_org["raw_key"]

    # Create agent with no traces
    create_resp = await client.post(
        "/agents",
        json={"name": "Stats Test Agent"},
        headers=_auth_header(raw_key),
    )
    assert create_resp.status_code == 201
    agent = create_resp.json()

    resp = await client.get(
        f"/agents/{agent['id']}/stats",
        headers=_auth_header(raw_key),
    )
    assert resp.status_code == 200
    stats = resp.json()
    assert stats["total_calls"] == 0
    assert stats["cache_hits"] == 0
    assert stats["cache_hit_rate"] == 0.0
    assert stats["total_sessions"] == 0


async def test_agent_stats_with_traces(
    client: AsyncClient,
    seed_org: dict,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    raw_key = seed_org["raw_key"]
    org = seed_org["org"]

    # Create agent
    create_resp = await client.post(
        "/agents",
        json={"name": "Stats Agent With Data"},
        headers=_auth_header(raw_key),
    )
    assert create_resp.status_code == 201
    agent_data = create_resp.json()
    agent_id = uuid.UUID(agent_data["id"])

    # Seed some traces directly
    async with session_factory() as session:
        session_obj = AgentSession(
            organisation_id=org.id,
            agent_id=agent_id,
            external_session_id="stats-test-session",
        )
        session.add(session_obj)
        await session.flush()

        for i in range(5):
            trace = CallTrace(
                organisation_id=org.id,
                agent_id=agent_id,
                agent_session_id=session_obj.id,
                request_id=f"stats-trace-{uuid.uuid4().hex[:8]}",
                model_used="gpt-4o-mini",
                routing_mode="AUTO",
                intervention_mode="OBSERVE",
                cache_hit=(i < 2),  # 2 out of 5 are cache hits
                input_tokens=100,
                output_tokens=50,
                latency_ms=200,
            )
            session.add(trace)
        await session.commit()

    resp = await client.get(
        f"/agents/{agent_data['id']}/stats",
        headers=_auth_header(raw_key),
    )
    assert resp.status_code == 200
    stats = resp.json()
    assert stats["total_calls"] == 5
    assert stats["cache_hits"] == 2
    assert stats["cache_hit_rate"] == pytest.approx(0.4, abs=0.01)
    assert stats["total_sessions"] == 1
    assert stats["total_input_tokens"] == 500
    assert stats["total_output_tokens"] == 250

"""Tests for trace and session query endpoints."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Agent, AgentSession, CallTrace, InterventionMode, RoutingMode


def _auth_header(raw_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {raw_key}"}


@pytest.fixture
async def agent_with_traces(
    seed_org: dict,
    session_factory: async_sessionmaker[AsyncSession],
) -> dict:
    """Create an agent with sessions and traces for testing."""
    org = seed_org["org"]

    async with session_factory() as session:
        agent = Agent(
            organisation_id=org.id,
            name="Traced Agent",
            slug=f"traced-agent-{uuid.uuid4().hex[:6]}",
            routing_mode=RoutingMode.AUTO,
            intervention_mode=InterventionMode.OBSERVE,
        )
        session.add(agent)
        await session.flush()

        agent_session = AgentSession(
            organisation_id=org.id,
            agent_id=agent.id,
            external_session_id="test-session-001",
        )
        session.add(agent_session)
        await session.flush()

        # Create some traces
        traces = []
        for i in range(3):
            trace = CallTrace(
                organisation_id=org.id,
                agent_id=agent.id,
                agent_session_id=agent_session.id,
                request_id=f"chatcmpl-trace-{i}",
                model_used="gpt-4o-mini",
                provider="openai",
                routing_mode="AUTO",
                intervention_mode="OBSERVE",
                cache_hit=(i == 0),
                cache_tier="exact" if i == 0 else None,
                input_tokens=100 + i * 10,
                output_tokens=50 + i * 5,
                latency_ms=200 + i * 50,
            )
            session.add(trace)
            traces.append(trace)

        await session.commit()

        return {
            "agent": agent,
            "session": agent_session,
            "traces": traces,
        }


async def test_list_traces(
    client: AsyncClient,
    seed_org: dict,
    agent_with_traces: dict,
) -> None:
    raw_key = seed_org["raw_key"]
    resp = await client.get("/traces", headers=_auth_header(raw_key))
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert "total" in data
    assert len(data["data"]) > 0


async def test_list_traces_filter_by_agent(
    client: AsyncClient,
    seed_org: dict,
    agent_with_traces: dict,
) -> None:
    raw_key = seed_org["raw_key"]
    agent_id = str(agent_with_traces["agent"].id)
    resp = await client.get(
        f"/traces?agent_id={agent_id}",
        headers=_auth_header(raw_key),
    )
    assert resp.status_code == 200
    data = resp.json()
    for trace in data["data"]:
        assert trace["agent_id"] == agent_id


async def test_list_traces_filter_cache_hit(
    client: AsyncClient,
    seed_org: dict,
    agent_with_traces: dict,
) -> None:
    raw_key = seed_org["raw_key"]
    resp = await client.get(
        "/traces?cache_hit=true",
        headers=_auth_header(raw_key),
    )
    assert resp.status_code == 200
    data = resp.json()
    for trace in data["data"]:
        assert trace["cache_hit"] is True


async def test_get_trace(
    client: AsyncClient,
    seed_org: dict,
    agent_with_traces: dict,
) -> None:
    raw_key = seed_org["raw_key"]
    trace_id = str(agent_with_traces["traces"][0].id)
    resp = await client.get(
        f"/traces/{trace_id}",
        headers=_auth_header(raw_key),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == trace_id
    assert data["model_used"] == "gpt-4o-mini"


async def test_get_trace_not_found(
    client: AsyncClient,
    seed_org: dict,
) -> None:
    raw_key = seed_org["raw_key"]
    fake_id = str(uuid.uuid4())
    resp = await client.get(
        f"/traces/{fake_id}",
        headers=_auth_header(raw_key),
    )
    assert resp.status_code == 404


async def test_list_sessions(
    client: AsyncClient,
    seed_org: dict,
    agent_with_traces: dict,
) -> None:
    raw_key = seed_org["raw_key"]
    resp = await client.get("/sessions", headers=_auth_header(raw_key))
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert len(data["data"]) > 0


async def test_list_sessions_filter_by_agent(
    client: AsyncClient,
    seed_org: dict,
    agent_with_traces: dict,
) -> None:
    raw_key = seed_org["raw_key"]
    agent_id = str(agent_with_traces["agent"].id)
    resp = await client.get(
        f"/sessions?agent_id={agent_id}",
        headers=_auth_header(raw_key),
    )
    assert resp.status_code == 200


async def test_get_session(
    client: AsyncClient,
    seed_org: dict,
    agent_with_traces: dict,
) -> None:
    raw_key = seed_org["raw_key"]
    session_id = str(agent_with_traces["session"].id)
    resp = await client.get(
        f"/sessions/{session_id}",
        headers=_auth_header(raw_key),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == session_id
    assert "stats" in data


async def test_list_session_traces(
    client: AsyncClient,
    seed_org: dict,
    agent_with_traces: dict,
) -> None:
    raw_key = seed_org["raw_key"]
    session_id = str(agent_with_traces["session"].id)
    resp = await client.get(
        f"/sessions/{session_id}/traces",
        headers=_auth_header(raw_key),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["data"]) == 3

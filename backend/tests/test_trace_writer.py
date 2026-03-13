"""Tests for the trace writer service."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import CallTrace, RequestLog, RoutingDecisionLog
from app.services.trace_writer import TracePayload, write_trace


@pytest.fixture
def sample_payload(seed_org: dict) -> TracePayload:
    org = seed_org["org"]
    return TracePayload(
        org_id=str(org.id),
        request_id="chatcmpl-test123",
        model_requested="gpt-4o",
        model_used="gpt-4o-mini",
        provider="openai",
        routing_mode="AUTO",
        intervention_mode="OBSERVE",
        policy_action="observe_only",
        cache_hit=False,
        input_tokens=100,
        output_tokens=50,
        latency_ms=250,
        cost_without_asahi=0.005,
        cost_with_asahi=0.002,
        savings_usd=0.003,
        savings_pct=60.0,
        routing_reason="Auto routing selected gpt-4o-mini",
        routing_factors={"mode": "auto", "complexity": 0.2},
        routing_confidence=0.85,
    )


async def test_write_trace_creates_all_records(
    sample_payload: TracePayload,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """write_trace should create CallTrace, RequestLog, and RoutingDecisionLog."""
    await write_trace(sample_payload)

    async with session_factory() as session:
        # Check CallTrace
        traces = (
            await session.execute(
                select(CallTrace).where(CallTrace.request_id == "chatcmpl-test123")
            )
        ).scalars().all()
        assert len(traces) == 1
        trace = traces[0]
        assert trace.model_used == "gpt-4o-mini"
        assert trace.routing_mode == "AUTO"
        assert trace.input_tokens == 100
        assert trace.cache_hit is False

        # Check RequestLog
        logs = (
            await session.execute(
                select(RequestLog).where(RequestLog.request_id == "chatcmpl-test123")
            )
        ).scalars().all()
        assert len(logs) == 1
        log = logs[0]
        assert log.model_used == "gpt-4o-mini"
        assert float(log.savings_usd) == pytest.approx(0.003, abs=0.0001)

        # Check RoutingDecisionLog
        decisions = (
            await session.execute(
                select(RoutingDecisionLog).where(
                    RoutingDecisionLog.call_trace_id == trace.id
                )
            )
        ).scalars().all()
        assert len(decisions) == 1
        decision = decisions[0]
        assert decision.selected_model == "gpt-4o-mini"
        assert decision.routing_mode == "AUTO"
        assert float(decision.confidence) == pytest.approx(0.85, abs=0.01)


async def test_write_trace_with_cache_hit(
    seed_org: dict,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """write_trace should record cache hits correctly."""
    org = seed_org["org"]
    payload = TracePayload(
        org_id=str(org.id),
        request_id="chatcmpl-cache-test",
        model_used="cached",
        routing_mode="AUTO",
        intervention_mode="OBSERVE",
        cache_hit=True,
        cache_tier="exact",
        savings_pct=100.0,
    )
    await write_trace(payload)

    async with session_factory() as session:
        trace = (
            await session.execute(
                select(CallTrace).where(CallTrace.request_id == "chatcmpl-cache-test")
            )
        ).scalar_one()
        assert trace.cache_hit is True
        assert trace.cache_tier == "exact"


async def test_write_trace_with_agent(
    seed_org: dict,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """write_trace should link to agent when agent_id is provided."""
    org = seed_org["org"]
    # Create a test agent first
    from app.db.models import Agent, RoutingMode, InterventionMode

    async with session_factory() as session:
        agent = Agent(
            organisation_id=org.id,
            name="Trace Test Agent",
            slug=f"trace-test-{uuid.uuid4().hex[:6]}",
            routing_mode=RoutingMode.AUTO,
            intervention_mode=InterventionMode.OBSERVE,
        )
        session.add(agent)
        await session.commit()
        agent_id = str(agent.id)

    payload = TracePayload(
        org_id=str(org.id),
        agent_id=agent_id,
        request_id="chatcmpl-agent-test",
        model_used="gpt-4o",
        routing_mode="AUTO",
        intervention_mode="OBSERVE",
    )
    await write_trace(payload)

    async with session_factory() as session:
        trace = (
            await session.execute(
                select(CallTrace).where(CallTrace.request_id == "chatcmpl-agent-test")
            )
        ).scalar_one()
        assert str(trace.agent_id) == agent_id


async def test_write_trace_handles_errors_gracefully(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """write_trace should not raise on invalid org_id — just log the error."""
    payload = TracePayload(
        org_id="not-a-uuid",
        request_id="chatcmpl-error-test",
        model_used="gpt-4o",
    )
    # Should not raise
    await write_trace(payload)

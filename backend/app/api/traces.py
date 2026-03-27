"""Trace and session observability endpoints."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.db.models import AgentSession, ApiKey, CallTrace, RoutingDecisionLog

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory pub/sub for SSE live trace — lightweight, no Redis dependency
_trace_subscribers: dict[str, list[asyncio.Queue]] = {}


def publish_trace_event(org_id: str, trace_data: dict) -> None:
    """Publish a new trace event to all SSE subscribers for this org."""
    queues = _trace_subscribers.get(org_id, [])
    for q in queues:
        try:
            q.put_nowait(trace_data)
        except asyncio.QueueFull:
            pass  # Drop if subscriber is behind


async def _get_org_id(request: Request) -> uuid.UUID:
    org_id = getattr(request.state, "org_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organisation context required")
    return uuid.UUID(org_id)


def _serialize_trace(trace: CallTrace) -> dict:
    meta = trace.trace_metadata or {}
    risk_factors = meta.get("risk_factors") if meta else None
    cache_debug = meta.get("cache_debug") if meta else None
    routing_debug = meta.get("routing_debug") if meta else None
    intervention_debug = meta.get("intervention_debug") if meta else None

    return {
        "id": str(trace.id),
        "organisation_id": str(trace.organisation_id),
        "agent_id": str(trace.agent_id) if trace.agent_id else None,
        "agent_session_id": str(trace.agent_session_id) if trace.agent_session_id else None,
        "request_id": trace.request_id,
        "model_requested": trace.model_requested,
        "model_used": trace.model_used,
        "provider": trace.provider,
        "routing_mode": trace.routing_mode,
        "intervention_mode": trace.intervention_mode,
        "policy_action": trace.policy_action,
        "policy_reason": trace.policy_reason,
        "cache_hit": trace.cache_hit,
        "cache_tier": trace.cache_tier,
        "input_tokens": trace.input_tokens,
        "output_tokens": trace.output_tokens,
        "latency_ms": trace.latency_ms,
        "risk_score": float(trace.risk_score) if trace.risk_score is not None else None,
        "intervention_level": trace.intervention_level,
        "risk_factors": risk_factors,
        "cache_debug": cache_debug,
        "routing_debug": routing_debug,
        "intervention_debug": intervention_debug,
        "trace_metadata": meta,
        "created_at": trace.created_at.isoformat() if trace.created_at else None,
    }


def _serialize_session(session: AgentSession, trace_count: int = 0) -> dict:
    return {
        "id": str(session.id),
        "organisation_id": str(session.organisation_id),
        "agent_id": str(session.agent_id),
        "external_session_id": session.external_session_id,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "last_seen_at": session.last_seen_at.isoformat() if session.last_seen_at else None,
        "trace_count": trace_count,
    }


@router.get("/traces")
async def list_traces(
    request: Request,
    db: AsyncSession = Depends(get_db),
    agent_id: Optional[str] = Query(default=None),
    session_id: Optional[str] = Query(default=None),
    cache_hit: Optional[bool] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """List call traces with optional filters."""
    org_id = await _get_org_id(request)
    query = select(CallTrace).where(CallTrace.organisation_id == org_id)

    if agent_id:
        query = query.where(CallTrace.agent_id == uuid.UUID(agent_id))
    if session_id:
        query = query.where(CallTrace.agent_session_id == uuid.UUID(session_id))
    if cache_hit is not None:
        query = query.where(CallTrace.cache_hit == cache_hit)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(CallTrace.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    traces = result.scalars().all()

    return {
        "data": [_serialize_trace(t) for t in traces],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/traces/{trace_id}")
async def get_trace(
    trace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get a single call trace with its routing decision."""
    org_id = await _get_org_id(request)
    try:
        trace_uuid = uuid.UUID(trace_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid trace_id format")
    result = await db.execute(
        select(CallTrace).where(CallTrace.id == trace_uuid, CallTrace.organisation_id == org_id)
    )
    trace = result.scalar_one_or_none()
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")

    # Fetch associated routing decision
    routing_result = await db.execute(
        select(RoutingDecisionLog).where(RoutingDecisionLog.call_trace_id == trace.id)
    )
    routing_decision = routing_result.scalar_one_or_none()

    data = _serialize_trace(trace)
    if routing_decision:
        data["routing_decision"] = {
            "id": str(routing_decision.id),
            "selected_model": routing_decision.selected_model,
            "selected_provider": routing_decision.selected_provider,
            "confidence": float(routing_decision.confidence) if routing_decision.confidence else None,
            "decision_summary": routing_decision.decision_summary,
            "factors": routing_decision.factors or {},
        }

    return data


@router.get("/sessions")
async def list_sessions(
    request: Request,
    db: AsyncSession = Depends(get_db),
    agent_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """List agent sessions with trace counts."""
    org_id = await _get_org_id(request)

    # Subquery for trace counts
    trace_count_sq = (
        select(
            CallTrace.agent_session_id,
            func.count(CallTrace.id).label("trace_count"),
        )
        .where(CallTrace.organisation_id == org_id)
        .group_by(CallTrace.agent_session_id)
        .subquery()
    )

    query = select(AgentSession, trace_count_sq.c.trace_count).outerjoin(
        trace_count_sq, AgentSession.id == trace_count_sq.c.agent_session_id
    ).where(AgentSession.organisation_id == org_id)

    if agent_id:
        query = query.where(AgentSession.agent_id == uuid.UUID(agent_id))

    # Total count
    count_base = select(AgentSession).where(AgentSession.organisation_id == org_id)
    if agent_id:
        count_base = count_base.where(AgentSession.agent_id == uuid.UUID(agent_id))
    total = (await db.execute(select(func.count()).select_from(count_base.subquery()))).scalar() or 0

    query = query.order_by(AgentSession.started_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    rows = result.all()

    return {
        "data": [_serialize_session(row[0], row[1] or 0) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get a single session with summary stats."""
    org_id = await _get_org_id(request)
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id format")
    result = await db.execute(
        select(AgentSession).where(AgentSession.id == session_uuid, AgentSession.organisation_id == org_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get trace stats for this session
    from sqlalchemy import case, Integer
    stats_result = await db.execute(
        select(
            func.count(CallTrace.id).label("total_traces"),
            func.sum(case((CallTrace.cache_hit.is_(True), 1), else_=0)).label("cache_hits"),
            func.avg(CallTrace.latency_ms).label("avg_latency_ms"),
        ).where(
            CallTrace.agent_session_id == session.id,
            CallTrace.organisation_id == org_id,
        )
    )
    stats = stats_result.one_or_none()

    data = _serialize_session(session)
    data["stats"] = {
        "total_traces": stats[0] if stats else 0,
        "cache_hits": int(stats[1] or 0) if stats else 0,
        "avg_latency_ms": round(float(stats[2]), 2) if stats and stats[2] else None,
    }
    return data


@router.get("/sessions/{session_id}/traces")
async def list_session_traces(
    session_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    """List all traces for a specific session, ordered chronologically."""
    org_id = await _get_org_id(request)
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id format")
    result = await db.execute(
        select(AgentSession).where(AgentSession.id == session_uuid, AgentSession.organisation_id == org_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    result = await db.execute(
        select(CallTrace)
        .where(
            CallTrace.agent_session_id == session.id,
            CallTrace.organisation_id == org_id,
        )
        .order_by(CallTrace.created_at.asc())
        .limit(limit)
    )
    traces = result.scalars().all()
    return {"data": [_serialize_trace(t) for t in traces]}


@router.get("/sessions/{session_id}/graph")
async def get_session_graph(
    session_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get the step dependency graph for a session.

    Builds a graph from the session's call traces ordered chronologically.
    Each trace becomes a step; later steps depend on all earlier ones.
    """
    org_id = await _get_org_id(request)
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id format")
    result = await db.execute(
        select(AgentSession).where(AgentSession.id == session_uuid, AgentSession.organisation_id == org_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    result = await db.execute(
        select(CallTrace)
        .where(
            CallTrace.agent_session_id == session.id,
            CallTrace.organisation_id == org_id,
        )
        .order_by(CallTrace.created_at.asc())
    )
    traces = result.scalars().all()

    steps = []
    for i, trace in enumerate(traces, 1):
        steps.append({
            "step_number": i,
            "call_trace_id": str(trace.id),
            "model_used": trace.model_used,
            "cache_hit": trace.cache_hit,
            "latency_ms": trace.latency_ms,
            "created_at": trace.created_at.isoformat() if trace.created_at else None,
            "depends_on": list(range(1, i)) if i > 1 else [],
        })

    return {
        "session_id": session_id,
        "step_count": len(steps),
        "steps": steps,
    }


# ── SSE Live Trace Stream ────────────────────────────────────────────────


@router.get("/traces/live")
async def live_traces(
    request: Request,
    agent_id: Optional[str] = Query(default=None),
    token: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """SSE endpoint that streams new traces in real-time.

    Clients connect via EventSource. Each event is a JSON-serialized trace.
    Optional agent_id filter to only receive traces for a specific agent.
    Optional token query param for EventSource clients (which can't send headers).
    """
    # Try to get org_id from request.state (set by AuthMiddleware)
    org_id = getattr(request.state, "org_id", None)

    # If no org_id from middleware, try the token query param
    if not org_id and token:
        key_hash = hashlib.sha256(token.encode()).hexdigest()
        result = await db.execute(
            select(ApiKey).where(
                ApiKey.key_hash == key_hash,
                ApiKey.is_active.is_(True),
            )
        )
        api_key = result.scalar_one_or_none()
        if api_key:
            org_id = api_key.organisation_id

    if not org_id:
        raise HTTPException(status_code=403, detail="Organisation context required")
    org_str = str(org_id)

    agent_filter = None
    if agent_id:
        try:
            agent_filter = str(uuid.UUID(agent_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid agent_id format")

    queue: asyncio.Queue = asyncio.Queue(maxsize=100)

    # Register subscriber
    if org_str not in _trace_subscribers:
        _trace_subscribers[org_str] = []
    _trace_subscribers[org_str].append(queue)

    async def event_stream():
        try:
            # Send initial keepalive
            yield f"event: connected\ndata: {json.dumps({'status': 'connected'})}\n\n"
            while True:
                try:
                    trace_data = await asyncio.wait_for(queue.get(), timeout=30.0)
                    # Apply agent filter if specified
                    if agent_filter and trace_data.get("agent_id") != agent_filter:
                        continue
                    yield f"data: {json.dumps(trace_data)}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive comment every 30s
                    yield ": keepalive\n\n"
                except asyncio.CancelledError:
                    break
        finally:
            # Unregister subscriber
            subs = _trace_subscribers.get(org_str, [])
            if queue in subs:
                subs.remove(queue)
            if not subs and org_str in _trace_subscribers:
                del _trace_subscribers[org_str]

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

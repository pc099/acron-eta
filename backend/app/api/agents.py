"""Agent registry routes."""

from __future__ import annotations

import re
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.db.models import Agent, AgentSession, CallTrace, InterventionMode, MemberRole, ModelEndpoint, RoutingMode
from app.middleware.rbac import require_role

router = APIRouter()


class AgentCreateRequest(BaseModel):
    name: str
    slug: Optional[str] = None
    description: Optional[str] = None
    routing_mode: str = RoutingMode.AUTO.value
    intervention_mode: str = InterventionMode.OBSERVE.value
    model_endpoint_id: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class AgentUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    routing_mode: Optional[str] = None
    intervention_mode: Optional[str] = None
    model_endpoint_id: Optional[str] = None
    is_active: Optional[bool] = None
    metadata: Optional[dict] = None


class SessionCreateRequest(BaseModel):
    external_session_id: str


def _slugify(value: str) -> str:
    slug = value.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug[:255]


def _to_routing_mode(value: str) -> RoutingMode:
    try:
        return RoutingMode(value.upper())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid routing mode") from exc


def _to_intervention_mode(value: str) -> InterventionMode:
    try:
        return InterventionMode(value.upper())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid intervention mode") from exc


async def _get_org_id(request: Request) -> uuid.UUID:
    org_id = getattr(request.state, "org_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organisation context required")
    return uuid.UUID(org_id)


async def _resolve_model_endpoint(
    db: AsyncSession, org_id: uuid.UUID, model_endpoint_id: Optional[str]
) -> Optional[ModelEndpoint]:
    if not model_endpoint_id:
        return None
    endpoint = await db.get(ModelEndpoint, uuid.UUID(model_endpoint_id))
    if not endpoint or endpoint.organisation_id != org_id:
        raise HTTPException(status_code=404, detail="Model endpoint not found")
    return endpoint


def _serialize_agent(agent: Agent) -> dict:
    return {
        "id": str(agent.id),
        "name": agent.name,
        "slug": agent.slug,
        "description": agent.description,
        "routing_mode": agent.routing_mode.value,
        "intervention_mode": agent.intervention_mode.value,
        "model_endpoint_id": str(agent.model_endpoint_id) if agent.model_endpoint_id else None,
        "is_active": agent.is_active,
        "metadata": agent.metadata_ or {},
        "created_at": agent.created_at.isoformat(),
        "updated_at": agent.updated_at.isoformat() if agent.updated_at else None,
    }


@router.get("")
async def list_agents(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    org_id = await _get_org_id(request)
    result = await db.execute(
        select(Agent).where(Agent.organisation_id == org_id).order_by(Agent.created_at.desc())
    )
    agents = result.scalars().all()
    return {"data": [_serialize_agent(agent) for agent in agents]}


@router.post("", status_code=201, dependencies=[require_role(MemberRole.ADMIN)])
async def create_agent(
    body: AgentCreateRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> dict:
    org_id = await _get_org_id(request)
    await _resolve_model_endpoint(db, org_id, body.model_endpoint_id)

    slug = _slugify(body.slug or body.name)
    existing = await db.execute(
        select(Agent).where(Agent.organisation_id == org_id, Agent.slug == slug)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Agent slug already exists")

    agent = Agent(
        organisation_id=org_id,
        name=body.name,
        slug=slug,
        description=body.description,
        routing_mode=_to_routing_mode(body.routing_mode),
        intervention_mode=_to_intervention_mode(body.intervention_mode),
        model_endpoint_id=uuid.UUID(body.model_endpoint_id) if body.model_endpoint_id else None,
        metadata_=body.metadata,
    )
    db.add(agent)
    await db.flush()
    return _serialize_agent(agent)


@router.get("/{agent_id}")
async def get_agent(agent_id: str, request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    org_id = await _get_org_id(request)
    agent = await db.get(Agent, uuid.UUID(agent_id))
    if not agent or agent.organisation_id != org_id:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _serialize_agent(agent)


@router.patch("/{agent_id}", dependencies=[require_role(MemberRole.ADMIN)])
async def update_agent(
    agent_id: str, body: AgentUpdateRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> dict:
    org_id = await _get_org_id(request)
    agent = await db.get(Agent, uuid.UUID(agent_id))
    if not agent or agent.organisation_id != org_id:
        raise HTTPException(status_code=404, detail="Agent not found")

    await _resolve_model_endpoint(db, org_id, body.model_endpoint_id)

    if body.name is not None:
        agent.name = body.name
    if body.description is not None:
        agent.description = body.description
    if body.routing_mode is not None:
        agent.routing_mode = _to_routing_mode(body.routing_mode)
    if body.intervention_mode is not None:
        agent.intervention_mode = _to_intervention_mode(body.intervention_mode)
    if body.model_endpoint_id is not None:
        agent.model_endpoint_id = uuid.UUID(body.model_endpoint_id) if body.model_endpoint_id else None
    if body.is_active is not None:
        agent.is_active = body.is_active
    if body.metadata is not None:
        agent.metadata_ = body.metadata

    await db.flush()
    return _serialize_agent(agent)


@router.post("/{agent_id}/sessions", status_code=201)
async def create_agent_session(
    agent_id: str,
    body: SessionCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    org_id = await _get_org_id(request)
    agent = await db.get(Agent, uuid.UUID(agent_id))
    if not agent or agent.organisation_id != org_id:
        raise HTTPException(status_code=404, detail="Agent not found")

    existing = await db.execute(
        select(AgentSession).where(
            AgentSession.organisation_id == org_id,
            AgentSession.agent_id == agent.id,
            AgentSession.external_session_id == body.external_session_id,
        )
    )
    session = existing.scalar_one_or_none()
    if session is None:
        session = AgentSession(
            organisation_id=org_id,
            agent_id=agent.id,
            external_session_id=body.external_session_id,
        )
        db.add(session)
        await db.flush()

    return {
        "id": str(session.id),
        "agent_id": str(agent.id),
        "external_session_id": session.external_session_id,
        "started_at": session.started_at.isoformat(),
        "last_seen_at": session.last_seen_at.isoformat() if session.last_seen_at else None,
    }


@router.post("/{agent_id}/archive", dependencies=[require_role(MemberRole.ADMIN)])
async def archive_agent(
    agent_id: str, request: Request, db: AsyncSession = Depends(get_db)
) -> dict:
    """Archive an agent by setting is_active=False."""
    org_id = await _get_org_id(request)
    agent = await db.get(Agent, uuid.UUID(agent_id))
    if not agent or agent.organisation_id != org_id:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent.is_active = False
    await db.flush()
    await db.refresh(agent)
    return _serialize_agent(agent)


@router.get("/{agent_id}/stats")
async def get_agent_stats(
    agent_id: str, request: Request, db: AsyncSession = Depends(get_db)
) -> dict:
    """Get aggregate stats for an agent from its call traces."""
    org_id = await _get_org_id(request)
    agent = await db.get(Agent, uuid.UUID(agent_id))
    if not agent or agent.organisation_id != org_id:
        raise HTTPException(status_code=404, detail="Agent not found")

    result = await db.execute(
        select(
            func.count(CallTrace.id).label("total_calls"),
            func.sum(case((CallTrace.cache_hit.is_(True), 1), else_=0)).label("cache_hits"),
            func.avg(CallTrace.latency_ms).label("avg_latency_ms"),
            func.sum(CallTrace.input_tokens).label("total_input_tokens"),
            func.sum(CallTrace.output_tokens).label("total_output_tokens"),
        ).where(
            CallTrace.agent_id == agent.id,
            CallTrace.organisation_id == org_id,
        )
    )
    row = result.one()

    total_calls = row[0] or 0
    cache_hits = int(row[1] or 0)
    session_count_result = await db.execute(
        select(func.count(AgentSession.id)).where(
            AgentSession.agent_id == agent.id,
            AgentSession.organisation_id == org_id,
        )
    )
    session_count = session_count_result.scalar() or 0

    return {
        "agent_id": str(agent.id),
        "total_calls": total_calls,
        "cache_hits": cache_hits,
        "cache_hit_rate": round(cache_hits / total_calls, 4) if total_calls > 0 else 0.0,
        "avg_latency_ms": round(float(row[2]), 2) if row[2] else None,
        "total_input_tokens": int(row[3] or 0),
        "total_output_tokens": int(row[4] or 0),
        "total_sessions": session_count,
    }

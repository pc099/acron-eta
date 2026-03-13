"""Routing decision audit routes and constraint CRUD."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.db.models import MemberRole, RoutingConstraint, RoutingDecisionLog
from app.middleware.rbac import require_role
from app.schemas.routing import ConstraintCreate, ConstraintResponse, ConstraintUpdate
from app.services.rule_validator import validate_rule

router = APIRouter()


async def _get_org_id(request: Request) -> uuid.UUID:
    org_id = getattr(request.state, "org_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organisation context required")
    return uuid.UUID(org_id)


@router.get("/decisions")
async def list_routing_decisions(
    request: Request,
    db: AsyncSession = Depends(get_db),
    agent_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    org_id = await _get_org_id(request)
    query = select(RoutingDecisionLog).where(RoutingDecisionLog.organisation_id == org_id)
    if agent_id:
        query = query.where(RoutingDecisionLog.agent_id == uuid.UUID(agent_id))
    query = query.order_by(RoutingDecisionLog.created_at.desc()).limit(limit)

    result = await db.execute(query)
    rows = result.scalars().all()
    return {
        "data": [
            {
                "id": str(row.id),
                "agent_id": str(row.agent_id) if row.agent_id else None,
                "call_trace_id": str(row.call_trace_id) if row.call_trace_id else None,
                "routing_mode": row.routing_mode,
                "intervention_mode": row.intervention_mode,
                "selected_model": row.selected_model,
                "selected_provider": row.selected_provider,
                "confidence": float(row.confidence) if row.confidence is not None else None,
                "decision_summary": row.decision_summary,
                "factors": row.factors or {},
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }


# ---------------------------------------------------------------------------
# Constraint CRUD
# ---------------------------------------------------------------------------

def _serialize_constraint(row: RoutingConstraint) -> dict:
    """Convert a RoutingConstraint row to a response dict."""
    return {
        "id": str(row.id),
        "organisation_id": str(row.organisation_id),
        "agent_id": str(row.agent_id) if row.agent_id else None,
        "rule_type": row.rule_type,
        "rule_config": row.rule_config or {},
        "priority": row.priority,
        "is_active": row.is_active,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


@router.post("/constraints", status_code=201, dependencies=[require_role(MemberRole.ADMIN)])
async def create_constraint(
    body: ConstraintCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a routing constraint. Validates rule config before persisting."""
    org_id = await _get_org_id(request)

    errors = validate_rule(body.rule_type, body.rule_config)
    if errors:
        raise HTTPException(status_code=422, detail={"validation_errors": errors})

    constraint = RoutingConstraint(
        organisation_id=org_id,
        agent_id=body.agent_id,
        rule_type=body.rule_type,
        rule_config=body.rule_config,
        priority=body.priority,
    )
    db.add(constraint)
    await db.flush()
    await db.refresh(constraint)
    await db.commit()
    return {"data": _serialize_constraint(constraint)}


@router.get("/constraints")
async def list_constraints(
    request: Request,
    db: AsyncSession = Depends(get_db),
    agent_id: str | None = Query(default=None),
    active_only: bool = Query(default=True),
) -> dict:
    """List routing constraints for the organisation."""
    org_id = await _get_org_id(request)
    query = select(RoutingConstraint).where(RoutingConstraint.organisation_id == org_id)
    if agent_id:
        query = query.where(RoutingConstraint.agent_id == uuid.UUID(agent_id))
    if active_only:
        query = query.where(RoutingConstraint.is_active.is_(True))
    query = query.order_by(RoutingConstraint.priority.desc(), RoutingConstraint.created_at)

    result = await db.execute(query)
    rows = result.scalars().all()
    return {"data": [_serialize_constraint(row) for row in rows]}


@router.put("/constraints/{constraint_id}", dependencies=[require_role(MemberRole.ADMIN)])
async def update_constraint(
    constraint_id: uuid.UUID,
    body: ConstraintUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update a routing constraint."""
    org_id = await _get_org_id(request)
    result = await db.execute(
        select(RoutingConstraint).where(
            RoutingConstraint.id == constraint_id,
            RoutingConstraint.organisation_id == org_id,
        )
    )
    constraint = result.scalar_one_or_none()
    if not constraint:
        raise HTTPException(status_code=404, detail="Constraint not found")

    if body.rule_config is not None:
        errors = validate_rule(constraint.rule_type, body.rule_config)
        if errors:
            raise HTTPException(status_code=422, detail={"validation_errors": errors})
        constraint.rule_config = body.rule_config

    if body.priority is not None:
        constraint.priority = body.priority
    if body.is_active is not None:
        constraint.is_active = body.is_active

    await db.flush()
    await db.refresh(constraint)
    await db.commit()
    return {"data": _serialize_constraint(constraint)}


@router.delete("/constraints/{constraint_id}", dependencies=[require_role(MemberRole.ADMIN)])
async def delete_constraint(
    constraint_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Soft-delete a routing constraint (set is_active=False)."""
    org_id = await _get_org_id(request)
    result = await db.execute(
        select(RoutingConstraint).where(
            RoutingConstraint.id == constraint_id,
            RoutingConstraint.organisation_id == org_id,
        )
    )
    constraint = result.scalar_one_or_none()
    if not constraint:
        raise HTTPException(status_code=404, detail="Constraint not found")

    constraint.is_active = False
    await db.flush()
    await db.refresh(constraint)
    await db.commit()
    return {"data": _serialize_constraint(constraint)}

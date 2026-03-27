"""Intervention log and fleet overview routes."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.db.models import Agent, InterventionLog, InterventionMode

router = APIRouter()


async def _get_org_id(request: Request) -> uuid.UUID:
    org_id = getattr(request.state, "org_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organisation context required")
    return uuid.UUID(org_id)


@router.get("")
async def list_interventions(
    request: Request,
    db: AsyncSession = Depends(get_db),
    agent_id: str | None = Query(None),
    level: int | None = Query(None, ge=0, le=4),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    """List intervention logs with optional filters."""
    org_id = await _get_org_id(request)

    stmt = select(InterventionLog).where(
        InterventionLog.organisation_id == org_id
    )
    if agent_id:
        stmt = stmt.where(InterventionLog.agent_id == uuid.UUID(agent_id))
    if level is not None:
        stmt = stmt.where(InterventionLog.intervention_level == level)

    stmt = stmt.order_by(InterventionLog.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    logs = result.scalars().all()

    return {
        "data": [_serialize_log(log) for log in logs],
        "pagination": {"limit": limit, "offset": offset},
    }


@router.get("/stats")
async def intervention_stats(
    request: Request,
    db: AsyncSession = Depends(get_db),
    days: int = Query(30, ge=1, le=90),
) -> dict:
    """Intervention counts by level per day for charting."""
    org_id = await _get_org_id(request)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    stmt = (
        select(
            func.date(InterventionLog.created_at).label("day"),
            InterventionLog.intervention_level,
            func.count().label("count"),
        )
        .where(
            InterventionLog.organisation_id == org_id,
            InterventionLog.created_at >= since,
        )
        .group_by("day", InterventionLog.intervention_level)
        .order_by("day")
    )
    result = await db.execute(stmt)
    rows = result.all()

    return {
        "data": [
            {
                "day": str(row[0]),
                "level": row[1],
                "count": row[2],
            }
            for row in rows
        ],
        "days": days,
    }


@router.get("/fleet-overview")
async def fleet_overview(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Fleet-wide mode distribution and intervention summary."""
    org_id = await _get_org_id(request)

    # Mode distribution
    mode_stmt = (
        select(
            Agent.intervention_mode,
            func.count().label("count"),
        )
        .where(Agent.organisation_id == org_id, Agent.is_active.is_(True))
        .group_by(Agent.intervention_mode)
    )
    mode_result = await db.execute(mode_stmt)
    mode_rows = mode_result.all()

    # Intervention summary (last 30 days)
    since = datetime.now(timezone.utc) - timedelta(days=30)
    summary_stmt = (
        select(
            func.count().label("total"),
            func.sum(case((InterventionLog.was_blocked.is_(True), 1), else_=0)).label("blocked"),
            func.sum(case((InterventionLog.action_taken == "reroute", 1), else_=0)).label("rerouted"),
            func.sum(case((InterventionLog.action_taken == "augment", 1), else_=0)).label("augmented"),
            func.sum(case((InterventionLog.action_taken == "flag", 1), else_=0)).label("flagged"),
        )
        .where(
            InterventionLog.organisation_id == org_id,
            InterventionLog.created_at >= since,
        )
    )
    summary_result = await db.execute(summary_stmt)
    summary_row = summary_result.one()

    return {
        "mode_distribution": {
            row[0].value if hasattr(row[0], "value") else str(row[0]): row[1]
            for row in mode_rows
        },
        "intervention_summary": {
            "total": summary_row[0] or 0,
            "blocked": int(summary_row[1] or 0),
            "rerouted": int(summary_row[2] or 0),
            "augmented": int(summary_row[3] or 0),
            "flagged": int(summary_row[4] or 0),
            "period_days": 30,
        },
    }


def _serialize_log(log: InterventionLog) -> dict:
    return {
        "id": str(log.id),
        "organisation_id": str(log.organisation_id),
        "agent_id": str(log.agent_id) if log.agent_id else None,
        "call_trace_id": str(log.call_trace_id) if log.call_trace_id else None,
        "request_id": log.request_id,
        "intervention_level": log.intervention_level,
        "intervention_mode": log.intervention_mode,
        "risk_score": float(log.risk_score),
        "risk_factors": log.risk_factors or {},
        "action_taken": log.action_taken,
        "action_detail": log.action_detail,
        "original_model": log.original_model,
        "final_model": log.final_model,
        "prompt_modified": log.prompt_modified,
        "was_blocked": log.was_blocked,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }

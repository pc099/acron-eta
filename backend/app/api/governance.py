"""Governance routes — org-scoped.

GET /governance/audit — Paginated audit log
"""

import math
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.db.models import AuditLog, User

router = APIRouter()


def _get_org_id(request: Request) -> uuid.UUID:
    org_id = getattr(request.state, "org_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organisation context required")
    return uuid.UUID(org_id)


@router.get("/audit")
async def audit_log(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Paginated audit log for the organisation."""
    org_id = _get_org_id(request)

    base = select(AuditLog).where(AuditLog.organisation_id == org_id)

    # Count total
    count_query = select(func.count()).select_from(base.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    offset = (page - 1) * limit
    query = base.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    logs = result.scalars().all()

    # Resolve actor emails in bulk
    user_ids = {log.user_id for log in logs if log.user_id}
    actor_map: dict[uuid.UUID, str] = {}
    if user_ids:
        users_result = await db.execute(
            select(User).where(User.id.in_(user_ids))
        )
        for user in users_result.scalars().all():
            actor_map[user.id] = user.email

    return {
        "data": [
            {
                "id": str(log.id),
                "timestamp": log.created_at.isoformat(),
                "actor": actor_map.get(log.user_id, "system") if log.user_id else "system",
                "action": log.action,
                "resource": f"{log.resource_type}:{log.resource_id}" if log.resource_type else log.action,
                "ip_address": log.ip_address,
            }
            for log in logs
        ],
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": max(1, math.ceil(total / limit)),
        },
    }

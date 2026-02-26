"""Admin routes — internal management endpoints.

GET /admin/stats — System-wide stats (requires admin auth).
"""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.db.models import ApiKey, Organisation, RequestLog, User

router = APIRouter()


@router.get("/stats")
async def admin_stats(db: AsyncSession = Depends(get_db)):
    """System-wide statistics (for internal admin dashboard)."""
    org_count = await db.execute(select(func.count(Organisation.id)))
    user_count = await db.execute(select(func.count(User.id)))
    key_count = await db.execute(select(func.count(ApiKey.id)))
    request_count = await db.execute(select(func.count(RequestLog.id)))

    return {
        "organisations": org_count.scalar() or 0,
        "users": user_count.scalar() or 0,
        "api_keys": key_count.scalar() or 0,
        "total_requests": request_count.scalar() or 0,
    }

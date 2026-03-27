"""Cache management routes — cache warming, stats, and analytics."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.middleware.rbac import require_role
from app.db.models import MemberRole

router = APIRouter()


async def _get_org_id(request: Request) -> uuid.UUID:
    org_id = getattr(request.state, "org_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organisation context required")
    return uuid.UUID(org_id)


class CacheWarmEntry(BaseModel):
    query: str = Field(..., min_length=1)
    response: str = Field(..., min_length=1)
    model_used: str = Field(default="cached")


class CacheWarmRequest(BaseModel):
    entries: list[CacheWarmEntry] = Field(..., min_length=1, max_length=100)
    ttl: int = Field(default=86400, ge=60, le=604800)


@router.post("/warm", dependencies=[require_role(MemberRole.ADMIN)])
async def warm_cache(
    body: CacheWarmRequest,
    request: Request,
) -> dict:
    """Pre-populate exact cache from a list of query/response pairs.

    Useful for warming up frequently-asked queries after deployment or
    loading golden responses into cache for guided routing scenarios.
    """
    org_id = await _get_org_id(request)
    redis = getattr(request.app.state, "redis", None)
    if not redis:
        raise HTTPException(status_code=503, detail="Cache service unavailable")

    from app.services.cache import RedisCache

    cache = RedisCache(redis)
    entries_dicts = [
        {"query": e.query, "response": e.response, "model_used": e.model_used}
        for e in body.entries
    ]
    cached_count = await cache.warm(str(org_id), entries_dicts, ttl=body.ttl)

    return {
        "warmed": cached_count,
        "total": len(body.entries),
        "ttl": body.ttl,
    }


@router.get("/stats")
async def cache_stats(request: Request) -> dict:
    """Return in-memory cache metrics (exact hits, semantic hits, misses, promotions)."""
    redis = getattr(request.app.state, "redis", None)
    if not redis:
        return {"metrics": {"exact_hits": 0, "semantic_hits": 0, "misses": 0, "promotions": 0, "hit_rate": 0.0}}

    from app.services.cache import RedisCache

    cache = RedisCache(redis)
    return {"metrics": cache.metrics.to_dict()}


class CacheInvalidateRequest(BaseModel):
    """Request to invalidate cache entries."""

    pattern: str = Field(
        default="*",
        description="Glob pattern for cache keys to invalidate (e.g., 'cache:exact:*', '*model_abc*')",
    )
    reason: str = Field(..., min_length=1, description="Reason for invalidation (logged in audit)")


@router.post("/invalidate", dependencies=[require_role(MemberRole.ADMIN)])
async def invalidate_cache(
    body: CacheInvalidateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Invalidate cache entries matching a pattern.

    Supports glob patterns for selective invalidation:
    - `*` - Invalidate all cache entries for this org
    - `cache:exact:*` - Invalidate only exact cache entries
    - `*model_abc*` - Invalidate entries related to a specific model

    Invalidation is logged to the audit log for compliance.

    Use cases:
    - Agent config changed (routing mode, intervention mode)
    - Model endpoint updated or removed
    - Policy changes that affect responses
    - Manual cache clearing for testing
    """
    import logging
    from datetime import datetime, timezone

    logger = logging.getLogger(__name__)

    org_id = await _get_org_id(request)
    redis = getattr(request.app.state, "redis", None)
    if not redis:
        raise HTTPException(status_code=503, detail="Cache service unavailable")

    # Build Redis key pattern scoped to org
    redis_pattern = f"prod:{org_id}:{body.pattern}"

    # Scan and delete matching keys
    invalidated_count = 0
    cursor = 0

    while True:
        cursor, keys = await redis.scan(cursor, match=redis_pattern, count=100)
        if keys:
            await redis.delete(*keys)
            invalidated_count += len(keys)

        if cursor == 0:
            break

    # Log invalidation to audit log
    try:
        from app.db.models import AuditLog

        audit_entry = AuditLog(
            organisation_id=org_id,
            user_id=getattr(request.state, "user_id", None),
            action="cache_invalidate",
            resource_type="cache",
            resource_id=None,
            details={
                "pattern": body.pattern,
                "redis_pattern": redis_pattern,
                "invalidated_count": invalidated_count,
                "reason": body.reason,
            },
            timestamp=datetime.now(timezone.utc),
        )
        db.add(audit_entry)
        await db.commit()
    except Exception as exc:
        logger.warning("Failed to log cache invalidation to audit: %s", exc)

    logger.info(
        "Cache invalidated",
        extra={
            "org_id": str(org_id),
            "pattern": body.pattern,
            "invalidated_count": invalidated_count,
            "reason": body.reason,
        },
    )

    return {
        "invalidated": invalidated_count,
        "pattern": body.pattern,
        "reason": body.reason,
    }

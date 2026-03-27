"""Analytics routes â€” all org-scoped.

GET /analytics/overview      â€” KPI cards
GET /analytics/savings       â€” Time series savings data
GET /analytics/models        â€” Cost breakdown by model
GET /analytics/cache         â€” Cache performance per tier
GET /analytics/latency       â€” p50/p90/p99 latency percentiles
GET /analytics/requests      â€” Paginated request log
GET /analytics/forecast      â€” Cost forecast
GET /analytics/recommendations â€” Optimization suggestions
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.db.models import CacheType, CallTrace, RequestLog, UsageSnapshot

router = APIRouter()


# â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _get_org_id(request: Request) -> uuid.UUID:
    org_id = getattr(request.state, "org_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organisation context required")
    return uuid.UUID(org_id)


def _period_to_timedelta(period: str) -> timedelta:
    mapping = {"7d": 7, "30d": 30, "90d": 90}
    days = mapping.get(period, 30)
    return timedelta(days=days)


# â”€â”€ Overview â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class OverviewResponse(BaseModel):
    period: str
    total_requests: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost_without_asahi: float
    total_cost_with_asahi: float
    total_savings_usd: float
    average_savings_pct: float
    cache_hit_rate: float
    cache_hits: dict
    avg_latency_ms: float
    p99_latency_ms: Optional[int]
    savings_delta_pct: float
    requests_delta_pct: float


@router.get("/overview", response_model=OverviewResponse)
async def analytics_overview(
    request: Request,
    period: str = Query("30d", pattern="^(7d|30d|90d)$"),
    db: AsyncSession = Depends(get_db),
):
    """KPI cards: total savings, requests, cache hit rate, latency."""
    org_id = _get_org_id(request)
    delta = _period_to_timedelta(period)
    now = datetime.now(timezone.utc)
    since = now - delta
    prev_since = since - delta  # Previous period for delta comparison

    # Current period
    current = await _aggregate_period(db, org_id, since, now)
    # Previous period
    previous = await _aggregate_period(db, org_id, prev_since, since)

    # Compute deltas
    savings_delta = 0.0
    if previous["total_savings_usd"] > 0:
        savings_delta = (
            (current["total_savings_usd"] - previous["total_savings_usd"])
            / previous["total_savings_usd"]
            * 100
        )

    requests_delta = 0.0
    if previous["total_requests"] > 0:
        requests_delta = (
            (current["total_requests"] - previous["total_requests"])
            / previous["total_requests"]
            * 100
        )

    return OverviewResponse(
        period=period,
        total_requests=current["total_requests"],
        total_input_tokens=current["total_input_tokens"],
        total_output_tokens=current["total_output_tokens"],
        total_cost_without_asahi=current["total_cost_without_asahi"],
        total_cost_with_asahi=current["total_cost_with_asahi"],
        total_savings_usd=current["total_savings_usd"],
        average_savings_pct=current["average_savings_pct"],
        cache_hit_rate=current["cache_hit_rate"],
        cache_hits=current["cache_hits"],
        avg_latency_ms=current["avg_latency_ms"],
        p99_latency_ms=current["p99_latency_ms"],
        savings_delta_pct=round(savings_delta, 1),
        requests_delta_pct=round(requests_delta, 1),
    )


async def _aggregate_period(
    db: AsyncSession, org_id: uuid.UUID, since: datetime, until: datetime
) -> dict:
    """Aggregate request log metrics for a time period."""
    result = await db.execute(
        select(
            func.count(RequestLog.id).label("total_requests"),
            func.coalesce(func.sum(RequestLog.input_tokens), 0).label("total_input_tokens"),
            func.coalesce(func.sum(RequestLog.output_tokens), 0).label("total_output_tokens"),
            func.coalesce(func.sum(RequestLog.cost_without_asahi), 0).label("total_cost_without"),
            func.coalesce(func.sum(RequestLog.cost_with_asahi), 0).label("total_cost_with"),
            func.coalesce(func.sum(RequestLog.savings_usd), 0).label("total_savings"),
            func.coalesce(func.avg(RequestLog.savings_pct), 0).label("avg_savings_pct"),
            func.sum(case((RequestLog.cache_hit.is_(True), 1), else_=0)).label("cache_hits_total"),
            func.coalesce(func.avg(RequestLog.latency_ms), 0).label("avg_latency"),
            # Cache tier breakdown
            func.sum(
                case((RequestLog.cache_tier == CacheType.EXACT, 1), else_=0)
            ).label("tier1_hits"),
            func.sum(
                case((RequestLog.cache_tier == CacheType.SEMANTIC, 1), else_=0)
            ).label("tier2_hits"),
            func.sum(
                case((RequestLog.cache_tier == CacheType.INTERMEDIATE, 1), else_=0)
            ).label("tier3_hits"),
        ).where(
            RequestLog.organisation_id == org_id,
            RequestLog.created_at >= since,
            RequestLog.created_at < until,
        )
    )
    row = result.one()

    total_requests = row.total_requests or 0
    cache_hits_total = row.cache_hits_total or 0
    cache_hit_rate = (cache_hits_total / total_requests) if total_requests > 0 else 0.0

    return {
        "total_requests": total_requests,
        "total_input_tokens": int(row.total_input_tokens),
        "total_output_tokens": int(row.total_output_tokens),
        "total_cost_without_asahi": float(row.total_cost_without),
        "total_cost_with_asahi": float(row.total_cost_with),
        "total_savings_usd": float(row.total_savings),
        "average_savings_pct": round(float(row.avg_savings_pct), 1),
        "cache_hit_rate": round(cache_hit_rate, 3),
        "cache_hits": {
            "tier1": int(row.tier1_hits or 0),
            "tier2": int(row.tier2_hits or 0),
            "tier3": int(row.tier3_hits or 0),
        },
        "avg_latency_ms": round(float(row.avg_latency), 1),
        "p99_latency_ms": None,  # Computed separately if needed
    }


# â”€â”€ Savings Time Series â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@router.get("/savings")
async def analytics_savings(
    request: Request,
    period: str = Query("30d", pattern="^(7d|30d|90d)$"),
    granularity: str = Query("day", pattern="^(hour|day)$"),
    db: AsyncSession = Depends(get_db),
):
    """Time series of savings data for charts."""
    org_id = _get_org_id(request)
    delta = _period_to_timedelta(period)
    since = datetime.now(timezone.utc) - delta

    if granularity == "day":
        trunc_fn = func.date_trunc("day", RequestLog.created_at)
    else:
        trunc_fn = func.date_trunc("hour", RequestLog.created_at)

    result = await db.execute(
        select(
            trunc_fn.label("timestamp"),
            func.coalesce(func.sum(RequestLog.cost_without_asahi), 0).label("cost_without_asahi"),
            func.coalesce(func.sum(RequestLog.cost_with_asahi), 0).label("cost_with_asahi"),
            func.coalesce(func.sum(RequestLog.savings_usd), 0).label("savings_usd"),
            func.count(RequestLog.id).label("requests"),
        )
        .where(
            RequestLog.organisation_id == org_id,
            RequestLog.created_at >= since,
        )
        .group_by(trunc_fn)
        .order_by(trunc_fn)
    )
    rows = result.all()

    return {
        "data": [
            {
                "timestamp": row.timestamp.isoformat(),
                "cost_without_asahi": float(row.cost_without_asahi),
                "cost_with_asahi": float(row.cost_with_asahi),
                "savings_usd": float(row.savings_usd),
                "requests": row.requests,
            }
            for row in rows
        ]
    }


# â”€â”€ Model Breakdown â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@router.get("/models")
async def analytics_models(
    request: Request,
    period: str = Query("30d", pattern="^(7d|30d|90d)$"),
    db: AsyncSession = Depends(get_db),
):
    """Cost breakdown by model (for pie chart)."""
    org_id = _get_org_id(request)
    since = datetime.now(timezone.utc) - _period_to_timedelta(period)

    result = await db.execute(
        select(
            RequestLog.model_used,
            func.count(RequestLog.id).label("requests"),
            func.coalesce(func.sum(RequestLog.cost_with_asahi), 0).label("total_cost"),
            func.coalesce(func.sum(RequestLog.savings_usd), 0).label("total_savings"),
        )
        .where(
            RequestLog.organisation_id == org_id,
            RequestLog.created_at >= since,
        )
        .group_by(RequestLog.model_used)
        .order_by(func.sum(RequestLog.cost_with_asahi).desc())
        .limit(20)
    )
    rows = result.all()

    return {
        "data": [
            {
                "model": row.model_used,
                "requests": row.requests,
                "total_cost": float(row.total_cost),
                "total_savings": float(row.total_savings),
            }
            for row in rows
        ]
    }


# â”€â”€ Cache Performance â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@router.get("/cache")
async def analytics_cache(
    request: Request,
    period: str = Query("30d", pattern="^(7d|30d|90d)$"),
    db: AsyncSession = Depends(get_db),
):
    """Cache performance breakdown by tier."""
    org_id = _get_org_id(request)
    since = datetime.now(timezone.utc) - _period_to_timedelta(period)

    result = await db.execute(
        select(
            func.count(RequestLog.id).label("total"),
            func.sum(case((RequestLog.cache_hit.is_(True), 1), else_=0)).label("hits"),
            func.sum(case((RequestLog.cache_tier == CacheType.EXACT, 1), else_=0)).label("tier1"),
            func.sum(case((RequestLog.cache_tier == CacheType.SEMANTIC, 1), else_=0)).label("tier2"),
            func.sum(case((RequestLog.cache_tier == CacheType.INTERMEDIATE, 1), else_=0)).label("tier3"),
        ).where(
            RequestLog.organisation_id == org_id,
            RequestLog.created_at >= since,
        )
    )
    row = result.one()
    total = row.total or 1

    return {
        "total_requests": total,
        "cache_hit_rate": round((row.hits or 0) / total, 3),
        "tiers": {
            "exact": {"hits": int(row.tier1 or 0), "rate": round((row.tier1 or 0) / total, 3)},
            "semantic": {"hits": int(row.tier2 or 0), "rate": round((row.tier2 or 0) / total, 3)},
            "intermediate": {"hits": int(row.tier3 or 0), "rate": round((row.tier3 or 0) / total, 3)},
        },
    }


# â”€â”€ Latency Percentiles â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@router.get("/latency")
async def analytics_latency(
    request: Request,
    period: str = Query("30d", pattern="^(7d|30d|90d)$"),
    db: AsyncSession = Depends(get_db),
):
    """p50, p90, p99 latency percentiles."""
    org_id = _get_org_id(request)
    since = datetime.now(timezone.utc) - _period_to_timedelta(period)

    result = await db.execute(
        select(
            func.percentile_cont(0.5).within_group(RequestLog.latency_ms).label("p50"),
            func.percentile_cont(0.9).within_group(RequestLog.latency_ms).label("p90"),
            func.percentile_cont(0.95).within_group(RequestLog.latency_ms).label("p95"),
            func.percentile_cont(0.99).within_group(RequestLog.latency_ms).label("p99"),
            func.avg(RequestLog.latency_ms).label("avg"),
        ).where(
            RequestLog.organisation_id == org_id,
            RequestLog.created_at >= since,
            RequestLog.latency_ms.isnot(None),
        )
    )
    row = result.one()

    return {
        "p50": round(float(row.p50 or 0), 1),
        "p90": round(float(row.p90 or 0), 1),
        "p95": round(float(row.p95 or 0), 1),
        "p99": round(float(row.p99 or 0), 1),
        "avg": round(float(row.avg or 0), 1),
    }


# â”€â”€ Request Log (Paginated) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@router.get("/requests")
async def analytics_requests(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    model: Optional[str] = None,
    cache_hit: Optional[bool] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
):
    """Paginated request log with filters, including risk data from CallTrace."""
    org_id = _get_org_id(request)

    # Outer-join CallTrace to get risk_score and intervention_level
    query = (
        select(RequestLog, CallTrace)
        .outerjoin(CallTrace, CallTrace.request_log_id == RequestLog.id)
        .where(RequestLog.organisation_id == org_id)
    )

    if model:
        query = query.where(RequestLog.model_used == model)
    if cache_hit is not None:
        query = query.where(RequestLog.cache_hit == cache_hit)
    if date_from:
        query = query.where(RequestLog.created_at >= date_from)
    if date_to:
        query = query.where(RequestLog.created_at <= date_to)

    # Count total (on RequestLog only)
    count_base = select(RequestLog).where(RequestLog.organisation_id == org_id)
    if model:
        count_base = count_base.where(RequestLog.model_used == model)
    if cache_hit is not None:
        count_base = count_base.where(RequestLog.cache_hit == cache_hit)
    if date_from:
        count_base = count_base.where(RequestLog.created_at >= date_from)
    if date_to:
        count_base = count_base.where(RequestLog.created_at <= date_to)
    count_query = select(func.count()).select_from(count_base.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    offset = (page - 1) * limit
    query = query.order_by(RequestLog.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    rows = result.all()

    data = []
    for row in rows:
        log = row[0]
        trace = row[1]

        # Extract metadata from trace_metadata (Python, not SQL — avoids SQLite JSON issues)
        risk_factors = None
        cache_debug = None
        routing_debug = None
        intervention_debug = None
        if trace and trace.trace_metadata:
            meta = trace.trace_metadata
            risk_factors = meta.get("risk_factors")
            cache_debug = meta.get("cache_debug")
            routing_debug = meta.get("routing_debug")
            intervention_debug = meta.get("intervention_debug")

        # Build asahio metadata object for consistency with gateway response
        asahio_meta = {
            "cache_hit": log.cache_hit,
            "cache_tier": log.cache_tier.value if log.cache_tier else None,
            "model_requested": log.model_requested,
            "model_used": log.model_used,
            "provider": log.provider,
            "routing_mode": log.routing_mode,
            "intervention_mode": trace.intervention_mode if trace else None,
            "cost_without_asahio": float(log.cost_without_asahi),
            "cost_with_asahio": float(log.cost_with_asahi),
            "cost_without_asahi": float(log.cost_without_asahi),  # backward compat
            "cost_with_asahi": float(log.cost_with_asahi),  # backward compat
            "savings_usd": float(log.savings_usd),
            "savings_pct": float(log.savings_pct) if log.savings_pct else None,
            "risk_score": float(trace.risk_score) if trace and trace.risk_score is not None else None,
            "risk_factors": risk_factors,
            "intervention_level": trace.intervention_level if trace else None,
            "request_id": trace.request_id if trace else None,
            "cache_debug": cache_debug,
            "routing_debug": routing_debug,
            "intervention_debug": intervention_debug,
        }

        data.append({
            "id": str(log.id),
            "call_trace_id": str(trace.id) if trace else None,
            "agent_id": str(trace.agent_id) if trace and trace.agent_id else None,
            "model_requested": log.model_requested,
            "model_used": log.model_used,
            "provider": log.provider,
            "routing_mode": log.routing_mode,
            "input_tokens": log.input_tokens,
            "output_tokens": log.output_tokens,
            "cost_without_asahi": float(log.cost_without_asahi),
            "cost_with_asahi": float(log.cost_with_asahi),
            "savings_usd": float(log.savings_usd),
            "savings_pct": float(log.savings_pct) if log.savings_pct else None,
            "cache_hit": log.cache_hit,
            "cache_tier": log.cache_tier.value if log.cache_tier else None,
            "latency_ms": log.latency_ms,
            "status_code": log.status_code,
            "risk_score": float(trace.risk_score) if trace and trace.risk_score is not None else None,
            "intervention_level": trace.intervention_level if trace else None,
            "risk_factors": risk_factors,
            "created_at": log.created_at.isoformat(),
            "asahio": asahio_meta,
            "asahi": asahio_meta,  # backward compat alias
        })

    return {
        "data": data,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": (total + limit - 1) // limit,
        },
    }


# â”€â”€ Forecast â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@router.get("/forecast")
async def analytics_forecast(
    request: Request,
    days: int = Query(30, ge=7, le=90),
    db: AsyncSession = Depends(get_db),
):
    """Simple cost forecast based on recent usage trends."""
    org_id = _get_org_id(request)
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=7)

    result = await db.execute(
        select(
            func.count(RequestLog.id).label("requests"),
            func.coalesce(func.sum(RequestLog.cost_with_asahi), 0).label("total_cost"),
            func.coalesce(func.sum(RequestLog.savings_usd), 0).label("total_savings"),
        ).where(
            RequestLog.organisation_id == org_id,
            RequestLog.created_at >= since,
        )
    )
    row = result.one()

    daily_cost = float(row.total_cost) / 7
    daily_savings = float(row.total_savings) / 7
    daily_requests = (row.requests or 0) / 7

    return {
        "forecast_days": days,
        "projected_cost_usd": round(daily_cost * days, 2),
        "projected_savings_usd": round(daily_savings * days, 2),
        "projected_requests": round(daily_requests * days),
        "daily_avg_cost": round(daily_cost, 4),
        "daily_avg_savings": round(daily_savings, 4),
    }


# â”€â”€ Recommendations â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@router.get("/recommendations")
async def analytics_recommendations(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Optimization suggestions based on usage patterns."""
    org_id = _get_org_id(request)
    since = datetime.now(timezone.utc) - timedelta(days=30)

    # Get cache hit rate
    cache_result = await db.execute(
        select(
            func.count(RequestLog.id).label("total"),
            func.sum(case((RequestLog.cache_hit.is_(True), 1), else_=0)).label("hits"),
        ).where(
            RequestLog.organisation_id == org_id,
            RequestLog.created_at >= since,
        )
    )
    cache_row = cache_result.one()
    total = cache_row.total or 1
    hit_rate = (cache_row.hits or 0) / total

    recommendations = []

    if hit_rate < 0.5:
        recommendations.append({
            "type": "cache",
            "title": "Enable semantic caching",
            "description": f"Your cache hit rate is {hit_rate:.0%}. Enabling semantic caching could save up to 40% more on repeated similar queries.",
            "impact": "high",
        })

    if total > 50000:
        recommendations.append({
            "type": "routing",
            "title": "Use AUTO routing mode",
            "description": "With your request volume, AUTO routing could save 30-60% by selecting cheaper models for simpler tasks.",
            "impact": "high",
        })

    if total < 100:
        recommendations.append({
            "type": "onboarding",
            "title": "Increase API usage",
            "description": "You're only making a few requests. The more traffic you route through ASAHIO, the more you save.",
            "impact": "medium",
        })

    return {"recommendations": recommendations}


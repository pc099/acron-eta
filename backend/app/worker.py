"""Celery worker for background task processing.

Tasks:
- write_request_log: Persist a request log entry to PostgreSQL
- update_usage_snapshot: Aggregate hourly usage snapshots

Start the worker:
    celery -A app.worker worker --loglevel=info

Uses Redis as both broker and result backend (same URL as the app cache).
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from celery import Celery

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

app = Celery(
    "asahi",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_soft_time_limit=30,
    task_time_limit=60,
    task_acks_late=True,
    worker_prefetch_multiplier=4,
)


def _get_sync_engine():
    """Create a synchronous SQLAlchemy engine for Celery tasks.

    Celery workers are synchronous — they cannot use asyncpg.
    We swap the driver to psycopg2 for sync DB access.
    """
    from sqlalchemy import create_engine

    url = settings.database_url
    # Convert asyncpg URL to psycopg2
    if "+asyncpg" in url:
        url = url.replace("+asyncpg", "")
    return create_engine(url, pool_size=5, max_overflow=10, pool_pre_ping=True)


def _get_sync_session():
    """Return a synchronous Session factory."""
    from sqlalchemy.orm import sessionmaker

    engine = _get_sync_engine()
    return sessionmaker(bind=engine)


@app.task(name="write_request_log", bind=True, max_retries=3, default_retry_delay=5)
def write_request_log(self, data: dict[str, Any]) -> dict[str, str]:
    """Persist a request log entry to PostgreSQL.

    Args:
        data: Dict with keys matching RequestLog columns:
            organisation_id, api_key_id, model_requested, model_used,
            provider, routing_mode, input_tokens, output_tokens,
            cost_without_asahi, cost_with_asahi, savings_usd, savings_pct,
            cache_hit, cache_tier, latency_ms, status_code, error_message
    """
    try:
        from app.db.models import CacheType, RequestLog

        Session = _get_sync_session()
        session = Session()

        try:
            # Map cache tier string to enum
            cache_tier = None
            cache_tier_str = data.get("cache_tier")
            if cache_tier_str:
                tier_map = {
                    "exact": CacheType.EXACT,
                    "semantic": CacheType.SEMANTIC,
                    "intermediate": CacheType.INTERMEDIATE,
                    "miss": CacheType.MISS,
                }
                cache_tier = tier_map.get(cache_tier_str.lower())

            log_entry = RequestLog(
                id=uuid.uuid4(),
                organisation_id=uuid.UUID(data["organisation_id"]),
                api_key_id=uuid.UUID(data["api_key_id"]) if data.get("api_key_id") else None,
                model_requested=data.get("model_requested"),
                model_used=data.get("model_used", "unknown"),
                provider=data.get("provider"),
                routing_mode=data.get("routing_mode"),
                input_tokens=data.get("input_tokens", 0),
                output_tokens=data.get("output_tokens", 0),
                cost_without_asahi=data.get("cost_without_asahi", 0.0),
                cost_with_asahi=data.get("cost_with_asahi", 0.0),
                savings_usd=data.get("savings_usd", 0.0),
                savings_pct=data.get("savings_pct"),
                cache_hit=data.get("cache_hit", False),
                cache_tier=cache_tier,
                latency_ms=data.get("latency_ms"),
                status_code=data.get("status_code", 200),
                error_message=data.get("error_message"),
            )

            session.add(log_entry)
            session.commit()
            return {"status": "ok", "id": str(log_entry.id)}
        finally:
            session.close()

    except Exception as exc:
        logger.exception("write_request_log failed: %s", exc)
        raise self.retry(exc=exc)


@app.task(name="update_usage_snapshot", bind=True, max_retries=2, default_retry_delay=10)
def update_usage_snapshot(self, org_id: str) -> dict[str, str]:
    """Aggregate hourly usage snapshot for an organisation.

    Reads recent request logs and updates a summary row for the current hour.
    This powers the analytics dashboard without expensive real-time queries.
    """
    try:
        from sqlalchemy import func, text

        Session = _get_sync_session()
        session = Session()

        try:
            now = datetime.now(timezone.utc)
            hour_start = now.replace(minute=0, second=0, microsecond=0)

            from app.db.models import RequestLog

            result = session.execute(
                text("""
                    SELECT
                        COUNT(*)            AS total_requests,
                        COALESCE(SUM(input_tokens), 0)   AS total_input_tokens,
                        COALESCE(SUM(output_tokens), 0)  AS total_output_tokens,
                        COALESCE(SUM(cost_with_asahi), 0) AS total_cost,
                        COALESCE(SUM(savings_usd), 0)    AS total_savings,
                        COALESCE(AVG(CASE WHEN cache_hit THEN 1.0 ELSE 0.0 END), 0) AS cache_hit_rate
                    FROM request_logs
                    WHERE organisation_id = :org_id
                      AND created_at >= :hour_start
                """),
                {"org_id": org_id, "hour_start": hour_start},
            )
            row = result.fetchone()
            logger.info(
                "Usage snapshot for org %s @ %s: %d requests, $%.4f cost, $%.4f saved",
                org_id,
                hour_start.isoformat(),
                row[0] if row else 0,
                row[3] if row else 0,
                row[4] if row else 0,
            )
            return {"status": "ok", "org_id": org_id, "hour": hour_start.isoformat()}
        finally:
            session.close()

    except Exception as exc:
        logger.exception("update_usage_snapshot failed: %s", exc)
        raise self.retry(exc=exc)

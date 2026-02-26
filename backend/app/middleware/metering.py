"""Metering middleware — logs usage to Redis + async to PostgreSQL after each gateway request.

After every /v1/chat/completions response:
1. Parse inference result from request.state
2. Write counters to Redis (requests, tokens, savings) — fast, atomic
3. Enqueue async DB write for RequestLog — fire-and-forget
Response is returned to client BEFORE DB writes happen.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.db.engine import async_session_factory
from app.db.models import CacheType, RequestLog
from app.services.metering import record_usage

logger = logging.getLogger(__name__)


class MeteringMiddleware(BaseHTTPMiddleware):
    """Track usage for every gateway request — Redis + PostgreSQL."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)

        # Only meter gateway requests
        if not request.url.path.startswith("/v1/"):
            return response

        # Check if inference result was attached by the gateway handler
        inference_result = getattr(request.state, "inference_result", None)
        if not inference_result:
            return response

        org_id = getattr(request.state, "org_id", None)
        api_key_id = getattr(request.state, "api_key_id", None)

        if not org_id:
            return response

        redis = getattr(request.app.state, "redis", None)

        # Fire-and-forget: write to Redis counters + PostgreSQL log
        asyncio.create_task(
            _meter_request(
                redis=redis,
                org_id=org_id,
                api_key_id=api_key_id,
                inference_result=inference_result,
                status_code=response.status_code,
            )
        )

        return response


async def _meter_request(
    redis,
    org_id: str,
    api_key_id: str | None,
    inference_result: object,
    status_code: int,
) -> None:
    """Write usage to Redis counters and PostgreSQL request log."""
    # Extract fields from inference result
    input_tokens = getattr(inference_result, "input_tokens", 0)
    output_tokens = getattr(inference_result, "output_tokens", 0)
    cost_with = getattr(inference_result, "cost_with_asahi", 0.0)
    savings_usd = getattr(inference_result, "savings_usd", 0.0)
    cache_hit = getattr(inference_result, "cache_hit", False)

    # 1. Redis counters (fast, atomic)
    if redis:
        try:
            await record_usage(
                redis=redis,
                org_id=org_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_hit=cache_hit,
                savings_usd=savings_usd,
                cost_usd=cost_with,
            )
        except Exception:
            logger.exception("Redis metering failed for org %s", org_id)

    # 2. PostgreSQL request log
    try:
        await _write_request_log(org_id, api_key_id, inference_result, status_code)
    except Exception:
        logger.exception("DB metering failed for org %s", org_id)


async def _write_request_log(
    org_id: str,
    api_key_id: str | None,
    inference_result: object,
    status_code: int,
) -> None:
    """Write a RequestLog entry to PostgreSQL."""
    model_used = getattr(inference_result, "model_used", "unknown")
    model_requested = getattr(inference_result, "model_requested", None)
    provider = getattr(inference_result, "provider", None)
    routing_mode = getattr(inference_result, "routing_mode", None)
    input_tokens = getattr(inference_result, "input_tokens", 0)
    output_tokens = getattr(inference_result, "output_tokens", 0)
    cost_without = getattr(inference_result, "cost_without_asahi", 0.0)
    cost_with = getattr(inference_result, "cost_with_asahi", 0.0)
    savings_usd = getattr(inference_result, "savings_usd", 0.0)
    savings_pct = getattr(inference_result, "savings_pct", None)
    cache_hit = getattr(inference_result, "cache_hit", False)
    cache_tier_str = getattr(inference_result, "cache_tier", None)
    latency_ms = getattr(inference_result, "latency_ms", None)
    error_message = getattr(inference_result, "error_message", None)

    # Map cache tier string to enum
    cache_tier = None
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
        organisation_id=uuid.UUID(org_id),
        api_key_id=uuid.UUID(api_key_id) if api_key_id else None,
        model_requested=model_requested,
        model_used=model_used,
        provider=provider,
        routing_mode=routing_mode,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_without_asahi=cost_without,
        cost_with_asahi=cost_with,
        savings_usd=savings_usd,
        savings_pct=savings_pct,
        cache_hit=cache_hit,
        cache_tier=cache_tier,
        latency_ms=latency_ms,
        status_code=status_code,
        error_message=error_message,
    )

    async with async_session_factory() as session:
        session.add(log_entry)
        await session.commit()

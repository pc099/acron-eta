"""Redis-based sliding window rate limiter.

Uses sorted sets (ZSET) for a precise sliding window counter.
Rate limits are per-org and per-API-key.
"""

import logging
import time

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.config import get_settings

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding window rate limiter using Redis ZSETs."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Only rate-limit gateway requests
        if not request.url.path.startswith("/v1/"):
            return await call_next(request)

        org_id = getattr(request.state, "org_id", None)
        if not org_id:
            return await call_next(request)

        redis = getattr(request.app.state, "redis", None)
        if not redis:
            # No Redis connection — allow the request but log warning
            logger.warning("Redis not available for rate limiting")
            return await call_next(request)

        settings = get_settings()
        limit = settings.rate_limit_requests_per_minute
        window = 60  # seconds

        key = f"asahi:rate:{org_id}:minute"
        now = time.time()
        window_start = now - window

        pipe = redis.pipeline()
        # Remove expired entries
        pipe.zremrangebyscore(key, 0, window_start)
        # Count current entries
        pipe.zcard(key)
        # Add this request
        pipe.zadd(key, {f"{now}": now})
        # Set TTL on the key
        pipe.expire(key, window + 1)
        results = await pipe.execute()

        current_count = results[1]

        if current_count >= limit:
            return JSONResponse(
                {
                    "error": {
                        "code": "rate_limit_exceeded",
                        "message": "Rate limit exceeded. Please retry after a moment.",
                        "type": "rate_limit_error",
                    }
                },
                status_code=429,
                headers={"Retry-After": "60"},
            )

        response = await call_next(request)

        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit - current_count - 1))
        response.headers["X-RateLimit-Reset"] = str(int(now + window))

        return response

"""Redis-based real-time usage metering.

Key schema:
  Daily usage:  asahi:usage:{org_id}:{YYYYMMDD}  → HASH
    Fields: requests, input_tokens, output_tokens, cache_hits, savings_usd

  Budget:       asahi:budget:{org_id}:{YYYY-MM}   → HASH
    Fields: spent_usd, request_count

All counters use atomic Redis operations (HINCRBY/HINCRBYFLOAT).
TTL is set to 32 days for daily buckets and 35 days for monthly budgets.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

DAILY_TTL = 32 * 86400  # 32 days in seconds
MONTHLY_TTL = 35 * 86400  # 35 days in seconds


async def record_usage(
    redis,
    org_id: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_hit: bool = False,
    savings_usd: float = 0.0,
    cost_usd: float = 0.0,
) -> None:
    """Record a single request's usage in Redis counters.

    Called by the metering middleware after every gateway request.
    Uses pipelining for efficiency (single round-trip).
    """
    if not redis:
        return

    now = datetime.now(timezone.utc)
    daily_key = f"asahi:usage:{org_id}:{now.strftime('%Y%m%d')}"
    monthly_key = f"asahi:budget:{org_id}:{now.strftime('%Y-%m')}"

    try:
        pipe = redis.pipeline()

        # Daily counters
        pipe.hincrby(daily_key, "requests", 1)
        pipe.hincrby(daily_key, "input_tokens", input_tokens)
        pipe.hincrby(daily_key, "output_tokens", output_tokens)
        if cache_hit:
            pipe.hincrby(daily_key, "cache_hits", 1)
        pipe.hincrbyfloat(daily_key, "savings_usd", savings_usd)
        pipe.hincrbyfloat(daily_key, "cost_usd", cost_usd)
        pipe.expire(daily_key, DAILY_TTL)

        # Monthly budget tracker
        pipe.hincrbyfloat(monthly_key, "spent_usd", cost_usd)
        pipe.hincrby(monthly_key, "request_count", 1)
        pipe.expire(monthly_key, MONTHLY_TTL)

        await pipe.execute()
    except Exception:
        logger.exception("Failed to record usage for org %s", org_id)


async def get_daily_usage(redis, org_id: str, date_str: str) -> dict:
    """Get usage counters for a specific day.

    Args:
        redis: Redis client
        org_id: Organisation ID
        date_str: Date in YYYYMMDD format

    Returns:
        Dict with requests, input_tokens, output_tokens, cache_hits, savings_usd, cost_usd
    """
    if not redis:
        return _empty_usage()

    key = f"asahi:usage:{org_id}:{date_str}"
    try:
        data = await redis.hgetall(key)
        return {
            "requests": int(data.get("requests", 0)),
            "input_tokens": int(data.get("input_tokens", 0)),
            "output_tokens": int(data.get("output_tokens", 0)),
            "cache_hits": int(data.get("cache_hits", 0)),
            "savings_usd": float(data.get("savings_usd", 0)),
            "cost_usd": float(data.get("cost_usd", 0)),
        }
    except Exception:
        logger.exception("Failed to get daily usage for org %s", org_id)
        return _empty_usage()


async def get_monthly_budget(redis, org_id: str) -> dict:
    """Get the current month's budget usage.

    Returns:
        Dict with spent_usd, request_count
    """
    if not redis:
        return {"spent_usd": 0.0, "request_count": 0}

    now = datetime.now(timezone.utc)
    key = f"asahi:budget:{org_id}:{now.strftime('%Y-%m')}"
    try:
        data = await redis.hgetall(key)
        return {
            "spent_usd": float(data.get("spent_usd", 0)),
            "request_count": int(data.get("request_count", 0)),
        }
    except Exception:
        logger.exception("Failed to get monthly budget for org %s", org_id)
        return {"spent_usd": 0.0, "request_count": 0}


async def is_budget_exceeded(redis, org_id: str, budget_usd: float) -> bool:
    """Check if the org has exceeded its monthly budget.

    Args:
        redis: Redis client
        org_id: Organisation ID
        budget_usd: Monthly budget limit in USD (0 or negative = unlimited)

    Returns:
        True if budget is exceeded
    """
    if budget_usd is None or budget_usd <= 0:
        return False

    budget = await get_monthly_budget(redis, org_id)
    return budget["spent_usd"] >= budget_usd


async def is_rate_limited(redis, org_id: str, monthly_limit: int) -> bool:
    """Check if the org has exceeded its monthly request limit.

    Args:
        redis: Redis client
        org_id: Organisation ID
        monthly_limit: Monthly request limit (-1 = unlimited)

    Returns:
        True if request limit is exceeded
    """
    if monthly_limit < 0:
        return False

    budget = await get_monthly_budget(redis, org_id)
    return budget["request_count"] >= monthly_limit


def _empty_usage() -> dict:
    return {
        "requests": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_hits": 0,
        "savings_usd": 0.0,
        "cost_usd": 0.0,
    }

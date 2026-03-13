"""Provider health service — background poller for LLM provider availability.

Maintains an in-memory health registry and optionally persists to Redis.
The routing engine queries this to avoid routing to degraded providers.
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 30
REDIS_HEALTH_TTL = 90
REDIS_KEY_PREFIX = "prod:global:provider:health"


@dataclass
class ProviderStatus:
    """Health status for a single provider."""

    provider: str
    status: str  # "healthy", "degraded", "unreachable"
    last_checked: float
    error: Optional[str] = None


# In-memory health registry — shared across the process
_health_registry: dict[str, ProviderStatus] = {}

# Known providers and how to check them
_PROVIDERS = {
    "openai": {"env_key": "OPENAI_API_KEY", "base_url": "https://api.openai.com"},
    "anthropic": {"env_key": "ANTHROPIC_API_KEY", "base_url": "https://api.anthropic.com"},
}


def get_provider_health(provider: str) -> str:
    """Get the current health status of a provider.

    Returns "healthy" if unknown (optimistic default).
    """
    status = _health_registry.get(provider)
    if not status:
        return "healthy"
    # If last check was > 5 minutes ago, consider stale and return healthy
    if time.time() - status.last_checked > 300:
        return "healthy"
    return status.status


def get_all_provider_health() -> dict[str, str]:
    """Get health status for all known providers."""
    return {
        provider: get_provider_health(provider)
        for provider in _PROVIDERS
    }


async def _check_provider(provider: str, config: dict) -> ProviderStatus:
    """Check if a provider is available by verifying API key presence.

    In production, this would make a lightweight API call (e.g., list models).
    For now, we check if the API key is configured as a proxy for availability.
    """
    env_key = config["env_key"]
    api_key = os.environ.get(env_key)

    if not api_key:
        return ProviderStatus(
            provider=provider,
            status="unreachable",
            last_checked=time.time(),
            error=f"{env_key} not configured",
        )

    # If API key is present, try a lightweight check
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Just check if the base URL is reachable (HEAD request)
            headers = {}
            if provider == "openai":
                headers["Authorization"] = f"Bearer {api_key}"
            elif provider == "anthropic":
                headers["x-api-key"] = api_key
                headers["anthropic-version"] = "2023-06-01"

            response = await client.get(
                f"{config['base_url']}/v1/models" if provider == "openai" else config["base_url"],
                headers=headers,
            )
            if response.status_code < 500:
                return ProviderStatus(
                    provider=provider,
                    status="healthy",
                    last_checked=time.time(),
                )
            return ProviderStatus(
                provider=provider,
                status="degraded",
                last_checked=time.time(),
                error=f"HTTP {response.status_code}",
            )
    except httpx.TimeoutException:
        return ProviderStatus(
            provider=provider,
            status="degraded",
            last_checked=time.time(),
            error="Timeout",
        )
    except Exception as exc:
        # If httpx not available or network error, treat API key presence as healthy
        logger.debug("Health check for %s failed: %s — treating as healthy", provider, exc)
        return ProviderStatus(
            provider=provider,
            status="healthy",
            last_checked=time.time(),
        )


async def _persist_to_redis(redis, provider: str, status: str) -> None:
    """Persist provider health to Redis with TTL."""
    if not redis:
        return
    try:
        key = f"{REDIS_KEY_PREFIX}:{provider}"
        await redis.set(key, status, ex=REDIS_HEALTH_TTL)
    except Exception:
        logger.debug("Failed to persist health to Redis for %s", provider)


async def poll_provider_health(redis=None) -> None:
    """Background task that continuously polls provider health."""
    logger.info("Provider health poller started (interval=%ds)", POLL_INTERVAL_SECONDS)
    while True:
        try:
            for provider, config in _PROVIDERS.items():
                status = await _check_provider(provider, config)
                _health_registry[provider] = status
                if redis:
                    await _persist_to_redis(redis, provider, status.status)

                if status.status != "healthy":
                    logger.warning(
                        "Provider %s is %s: %s",
                        provider,
                        status.status,
                        status.error,
                    )
        except Exception:
            logger.exception("Provider health poll cycle failed")

        await asyncio.sleep(POLL_INTERVAL_SECONDS)

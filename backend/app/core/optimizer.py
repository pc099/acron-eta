"""Bridge to the existing src/ InferenceOptimizer.

Provides a thin wrapper that adapts the existing synchronous
InferenceOptimizer for use in the async FastAPI gateway.
Integrates Redis cache (exact + semantic) before falling through
to the src/ optimizer.
"""

import asyncio
import logging
import sys
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Add the project root to sys.path so we can import from src/
PROJECT_ROOT = str(Path(__file__).resolve().parents[3])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@dataclass
class GatewayResult:
    """Normalized result from the optimizer for the gateway response."""

    response: str = ""
    model_used: str = "unknown"
    model_requested: Optional[str] = None
    provider: Optional[str] = None
    routing_mode: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_without_asahi: float = 0.0
    cost_with_asahi: float = 0.0
    savings_usd: float = 0.0
    savings_pct: Optional[float] = None
    cache_hit: bool = False
    cache_tier: Optional[str] = None
    latency_ms: Optional[int] = None
    routing_reason: Optional[str] = None
    error_message: Optional[str] = None


def _create_optimizer(use_mock: bool = True):
    """Create an InferenceOptimizer instance from the existing src/ code."""
    try:
        from src.core.optimizer import InferenceOptimizer

        return InferenceOptimizer(use_mock=use_mock)
    except Exception:
        logger.exception("Failed to create InferenceOptimizer")
        return None


@lru_cache(maxsize=1)
def get_optimizer_instance(use_mock: bool = True):
    """Get or create a cached optimizer instance."""
    return _create_optimizer(use_mock=use_mock)


async def run_inference(
    prompt: str,
    routing_mode: str = "autopilot",
    quality_preference: Optional[str] = "high",
    latency_preference: Optional[str] = "normal",
    model_override: Optional[str] = None,
    org_id: Optional[str] = None,
    use_mock: bool = True,
    redis=None,
) -> GatewayResult:
    """Run inference with Redis cache check, then fall through to optimizer.

    Flow:
    1. Check Redis exact cache (Tier 1)
    2. Check Redis semantic cache (Tier 2)
    3. On miss: call existing InferenceOptimizer.infer()
    4. Store result in Redis cache
    5. Return normalized GatewayResult
    """
    start_time = time.time()

    # ── Redis Cache Check ─────────────────────
    if redis and org_id:
        try:
            from app.services.cache import RedisCache

            cache = RedisCache(redis)
            hit = await cache.get(org_id, prompt, model=model_override)
            if hit:
                elapsed = int((time.time() - start_time) * 1000)
                logger.info(
                    "Cache %s hit for org %s (similarity=%.4f)",
                    hit.cache_tier,
                    org_id,
                    hit.similarity or 1.0,
                )
                return GatewayResult(
                    response=hit.response,
                    model_used=hit.model_used,
                    model_requested=model_override,
                    routing_mode=routing_mode.upper(),
                    input_tokens=0,
                    output_tokens=0,
                    cost_without_asahi=0.0,
                    cost_with_asahi=0.0,
                    savings_usd=0.0,
                    savings_pct=100.0,
                    cache_hit=True,
                    cache_tier=hit.cache_tier,
                    latency_ms=elapsed,
                    routing_reason=f"Cache {hit.cache_tier} hit",
                )
        except Exception:
            logger.exception("Redis cache check failed, falling through to optimizer")

    # ── Optimizer Inference ───────────────────
    optimizer = get_optimizer_instance(use_mock=use_mock)

    if not optimizer:
        return GatewayResult(
            response="Optimizer unavailable",
            error_message="Failed to initialize InferenceOptimizer",
        )

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: optimizer.infer(
                prompt=prompt,
                routing_mode=routing_mode.lower(),
                quality_preference=quality_preference,
                latency_preference=latency_preference,
                model_override=model_override,
                organization_id=org_id,
            ),
        )

        elapsed = int((time.time() - start_time) * 1000)

        # Map cache_tier int to string
        cache_tier_map = {0: None, 1: "exact", 2: "semantic", 3: "intermediate"}
        cache_tier = cache_tier_map.get(result.cache_tier, None)

        # Compute savings
        cost_original = result.cost_original or result.cost * 3
        cost_with = result.cost
        savings = cost_original - cost_with
        savings_pct = (savings / cost_original * 100) if cost_original > 0 else 0.0

        gateway_result = GatewayResult(
            response=result.response,
            model_used=result.model_used,
            model_requested=model_override,
            routing_mode=routing_mode.upper(),
            input_tokens=result.tokens_input,
            output_tokens=result.tokens_output,
            cost_without_asahi=cost_original,
            cost_with_asahi=cost_with,
            savings_usd=savings,
            savings_pct=round(savings_pct, 2),
            cache_hit=result.cache_hit,
            cache_tier=cache_tier,
            latency_ms=elapsed,
            routing_reason=result.routing_reason,
        )

        # ── Store in Redis Cache (fire-and-forget) ──
        if redis and org_id and result.response and not result.cache_hit:
            asyncio.create_task(
                _store_in_cache(redis, org_id, prompt, result.response, result.model_used)
            )

        return gateway_result

    except Exception as e:
        logger.exception("Inference failed for org %s", org_id)
        return GatewayResult(
            response="",
            error_message=str(e),
        )


async def _store_in_cache(
    redis, org_id: str, query: str, response: str, model_used: str
) -> None:
    """Fire-and-forget: store inference result in Redis cache."""
    try:
        from app.services.cache import RedisCache

        cache = RedisCache(redis)
        await cache.set(org_id, query, response, model_used)
    except Exception:
        logger.exception("Failed to cache result for org %s", org_id)

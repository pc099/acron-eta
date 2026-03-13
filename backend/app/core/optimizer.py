"""Bridge to the legacy optimizer used by the canonical ASAHIO backend."""

import asyncio
import logging
import sys
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = str(Path(__file__).resolve().parents[3])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

_ROUTING_MODE_ALIASES = {
    "AUTOPILOT": "AUTO",
    "AUTO": "AUTO",
    "GUIDED": "GUIDED",
    "EXPLICIT": "EXPLICIT",
}

_LEGACY_ROUTING_MODES = {
    "AUTO": "autopilot",
    "GUIDED": "guided",
    "EXPLICIT": "explicit",
}


@dataclass
class GatewayResult:
    """Normalized result from the optimizer for the gateway response."""

    response: str = ""
    request_id: Optional[str] = None
    model_used: str = "unknown"
    model_requested: Optional[str] = None
    provider: Optional[str] = None
    routing_mode: Optional[str] = None
    intervention_mode: Optional[str] = None
    agent_id: Optional[str] = None
    agent_session_id: Optional[str] = None
    model_endpoint_id: Optional[str] = None
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
    routing_factors: dict = field(default_factory=dict)
    routing_confidence: Optional[float] = None
    policy_action: str = "observe_only"
    policy_reason: Optional[str] = None
    error_message: Optional[str] = None


def normalize_routing_mode(value: Optional[str]) -> str:
    if not value:
        return "AUTO"
    return _ROUTING_MODE_ALIASES.get(value.upper(), value.upper())


def _legacy_routing_mode(value: Optional[str]) -> str:
    normalized = normalize_routing_mode(value)
    return _LEGACY_ROUTING_MODES.get(normalized, "autopilot")


def _create_optimizer(use_mock: bool = True):
    try:
        from src.core.optimizer import InferenceOptimizer

        return InferenceOptimizer(use_mock=use_mock)
    except Exception:
        logger.exception("Failed to create InferenceOptimizer")
        return None


@lru_cache(maxsize=1)
def get_optimizer_instance(use_mock: bool = True):
    return _create_optimizer(use_mock=use_mock)


async def run_inference(
    prompt: str,
    routing_mode: str = "AUTO",
    intervention_mode: str = "OBSERVE",
    quality_preference: Optional[str] = "high",
    latency_preference: Optional[str] = "normal",
    model_override: Optional[str] = None,
    org_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    agent_session_id: Optional[str] = None,
    model_endpoint_id: Optional[str] = None,
    provider_hint: Optional[str] = None,
    use_mock: bool = True,
    redis=None,
) -> GatewayResult:
    start_time = time.time()
    normalized_routing_mode = normalize_routing_mode(routing_mode)
    policy_reason = None
    if intervention_mode.upper() != "OBSERVE":
        policy_reason = (
            "Intervention mode is recorded for auditability. "
            "The intervention ladder is not yet active in the runtime path."
        )

    # Classify dependency level for context-aware caching
    dep_level = None
    try:
        from app.services.dependency_classifier import DependencyClassifier

        classifier = DependencyClassifier()
        dep_classification = classifier.classify(prompt)
        dep_level = dep_classification.level
    except Exception:
        logger.debug("Dependency classifier unavailable, defaulting to standard cache")

    if redis and org_id:
        try:
            from app.services.cache import RedisCache

            cache = RedisCache(redis)

            # Use context-aware cache if dependency level is available
            if dep_level is not None:
                from app.services.coherence_validator import CoherenceValidator

                validator = CoherenceValidator()
                hit = await cache.context_get(
                    org_id, prompt,
                    dependency_level=dep_level,
                    model=model_override,
                    coherence_validator=validator,
                )
            else:
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
                    provider=provider_hint,
                    routing_mode=normalized_routing_mode,
                    intervention_mode=intervention_mode.upper(),
                    agent_id=agent_id,
                    agent_session_id=agent_session_id,
                    model_endpoint_id=model_endpoint_id,
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
                    routing_factors={"cache": hit.cache_tier},
                    policy_action="observe_only",
                    policy_reason=policy_reason,
                )
        except Exception:
            logger.exception("Redis cache check failed, falling through to optimizer")

    # Run the routing engine to get model selection and factor breakdown
    from app.services.routing import RoutingContext, RoutingEngine

    routing_ctx = RoutingContext(
        prompt=prompt,
        routing_mode=normalized_routing_mode,
        quality_preference=quality_preference or "high",
        latency_preference=latency_preference or "normal",
        model_override=model_override,
        provider_hint=provider_hint,
    )
    routing_engine = RoutingEngine()
    routing_decision = routing_engine.route(routing_ctx)

    # Use routing decision to inform the model override if AUTO mode selected a model
    effective_model = model_override or routing_decision.selected_model

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
                routing_mode=_legacy_routing_mode(normalized_routing_mode),
                quality_preference=quality_preference,
                latency_preference=latency_preference,
                model_override=effective_model,
                organization_id=org_id,
            ),
        )

        elapsed = int((time.time() - start_time) * 1000)
        cache_tier_map = {0: None, 1: "exact", 2: "semantic", 3: "intermediate"}
        cache_tier = cache_tier_map.get(result.cache_tier, None)

        cost_original = result.cost_original or result.cost * 3
        cost_with = result.cost
        savings = cost_original - cost_with
        savings_pct = (savings / cost_original * 100) if cost_original > 0 else 0.0

        gateway_result = GatewayResult(
            response=result.response,
            request_id=getattr(result, "request_id", None),
            model_used=result.model_used,
            model_requested=model_override,
            provider=routing_decision.selected_provider or provider_hint,
            routing_mode=normalized_routing_mode,
            intervention_mode=intervention_mode.upper(),
            agent_id=agent_id,
            agent_session_id=agent_session_id,
            model_endpoint_id=model_endpoint_id,
            input_tokens=result.tokens_input,
            output_tokens=result.tokens_output,
            cost_without_asahi=cost_original,
            cost_with_asahi=cost_with,
            savings_usd=savings,
            savings_pct=round(savings_pct, 2),
            cache_hit=result.cache_hit,
            cache_tier=cache_tier,
            latency_ms=elapsed,
            routing_reason=routing_decision.reason,
            routing_factors=routing_decision.factors,
            routing_confidence=routing_decision.confidence,
            policy_action="observe_only",
            policy_reason=policy_reason,
        )

        if redis and org_id and result.response and not result.cache_hit:
            asyncio.create_task(
                _store_in_cache(redis, org_id, prompt, result.response, result.model_used)
            )

        return gateway_result
    except Exception as exc:
        logger.exception("Inference failed for org %s", org_id)
        return GatewayResult(response="", error_message=str(exc))


async def _store_in_cache(redis, org_id: str, query: str, response: str, model_used: str) -> None:
    try:
        from app.services.cache import RedisCache

        cache = RedisCache(redis)
        await cache.set(org_id, query, response, model_used)
    except Exception:
        logger.exception("Failed to cache result for org %s", org_id)

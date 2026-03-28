"""Bridge to the legacy optimizer used by the canonical ASAHIO backend.

Metrics are exported to Prometheus via /metrics endpoint.

The InferencePipeline class breaks the request lifecycle into discrete phases:
  1. score_risk        — sync <2ms risk estimate
  2. classify_dependency — dependency level for context-aware caching
  3. check_cache       — Redis exact / Pinecone semantic lookup
  4. evaluate_intervention — intervention ladder against risk score
  5. execute_chain     — GUIDED mode chain execution (optional)
  6. select_model      — routing engine model selection
  7. call_provider     — LLM inference via circuit breaker + retry
  8. build_response    — assemble GatewayResult + fire background tasks

The public run_inference() function delegates to InferencePipeline.execute().
"""

import asyncio
import logging
import sys
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from app.services.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitOpenError,
    execute_with_retry,
    RetryConfig,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-provider circuit breakers (module-level singletons)
# ---------------------------------------------------------------------------
_provider_circuits: dict[str, CircuitBreaker] = {}

_PROVIDER_CB_CONFIG = CircuitBreakerConfig(
    failure_threshold=5,
    recovery_timeout_seconds=30.0,
    half_open_max_calls=1,
    degraded_failure_threshold=2,
)

_PROVIDER_RETRY_CONFIG = RetryConfig(
    max_attempts=2,
    base_delay_seconds=0.5,
    max_delay_seconds=5.0,
    jitter=True,
)


def _get_circuit(provider: str, redis: Optional[Any] = None) -> CircuitBreaker:
    """Get or create a circuit breaker for a provider.

    Args:
        provider: Provider name (openai, anthropic, etc.)
        redis: Optional Redis connection for state persistence

    Returns:
        CircuitBreaker instance for the provider
    """
    if provider not in _provider_circuits:
        _provider_circuits[provider] = CircuitBreaker(provider, _PROVIDER_CB_CONFIG, redis)
    elif redis and not _provider_circuits[provider]._redis:
        # Update existing circuit with redis if it didn't have one before
        _provider_circuits[provider]._redis = redis
    return _provider_circuits[provider]

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
    routing_metadata: Optional[dict] = None  # Debug metadata: considered_models, selection_factors, confidence_breakdown
    policy_action: str = "observe_only"
    policy_reason: Optional[str] = None
    risk_score: Optional[float] = None
    risk_factors: dict = field(default_factory=dict)
    intervention_level: Optional[int] = None
    intervention_metadata: Optional[dict] = None  # Debug metadata: action, reasoning, prompt changes, model changes
    error_message: Optional[str] = None
    # SDK v2 tool support
    tools_called: Optional[dict] = None
    tool_call_count: int = 0
    # Cache decision metadata for debugging
    cache_metadata: Optional[dict] = None
    # ABA / Model C observation fields
    agent_type: Optional[str] = None  # CHATBOT, RAG, CODING, etc.
    complexity_score: Optional[float] = None  # 0.0-1.0 (use risk_score if not set)
    output_type: Optional[str] = None  # FACTUAL, CODE, CONVERSATIONAL, etc.
    hallucination_detected: bool = False


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


# ---------------------------------------------------------------------------
# InferencePipeline — one method per phase
# ---------------------------------------------------------------------------

class InferencePipeline:
    """Structured inference pipeline — one method per phase.

    Each phase is a separate method so it can be tested and reasoned about
    independently. The public execute() method orchestrates them in order.
    """

    def __init__(
        self,
        prompt: str,
        routing_mode: str,
        intervention_mode: str,
        quality_preference: Optional[str],
        latency_preference: Optional[str],
        model_override: Optional[str],
        org_id: Optional[str],
        agent_id: Optional[str],
        agent_session_id: Optional[str],
        model_endpoint_id: Optional[str],
        provider_hint: Optional[str],
        use_mock: bool,
        redis,
        session_step: Optional[int],
        fingerprint_hallucination_rate: Optional[float],
        agent_type: Optional[str],
        threshold_overrides: Optional[dict],
        chain_config: Optional[dict],
        bypass_cache: bool,
    ) -> None:
        self.prompt = prompt
        self.normalized_routing_mode = normalize_routing_mode(routing_mode)
        self.norm_intervention_mode = intervention_mode.upper()
        self.quality_preference = quality_preference
        self.latency_preference = latency_preference
        self.model_override = model_override
        self.org_id = org_id
        self.agent_id = agent_id
        self.agent_session_id = agent_session_id
        self.model_endpoint_id = model_endpoint_id
        self.provider_hint = provider_hint
        self.use_mock = use_mock
        self.redis = redis
        self.session_step = session_step
        self.fingerprint_hallucination_rate = fingerprint_hallucination_rate
        self.agent_type = agent_type
        self.threshold_overrides = threshold_overrides
        self.chain_config = chain_config
        self.bypass_cache = bypass_cache

        # Populated by pipeline phases
        self.start_time = time.time()
        self.risk_breakdown = None
        self.dep_level = None
        self.intervention_decision = None

    async def execute(self) -> GatewayResult:
        """Run the full inference pipeline."""
        self._score_risk()
        self._classify_dependency()

        cache_result = await self._check_cache()
        if cache_result is not None:
            return cache_result

        block_result = self._evaluate_intervention()
        if block_result is not None:
            return block_result

        chain_result = await self._execute_chain()
        if chain_result is not None:
            return chain_result

        return await self._route_and_call_provider()

    # -- Phase 1: Risk scoring (sync, <2ms) --------------------------------

    def _score_risk(self) -> None:
        """Compute fast risk estimate for the gateway critical path."""
        try:
            from app.services.risk_scorer import RiskScoringEngine

            risk_engine = RiskScoringEngine()
            self.risk_breakdown = risk_engine.fast_estimate(
                prompt=self.prompt,
                model_id=self.model_override,
                fingerprint_hallucination_rate=self.fingerprint_hallucination_rate,
                session_step=self.session_step,
            )
        except Exception:
            logger.warning("Risk scorer unavailable — skipping intervention", exc_info=True)

    # -- Phase 2: Dependency classification --------------------------------

    def _classify_dependency(self) -> None:
        """Classify dependency level for context-aware caching."""
        try:
            from app.services.dependency_classifier import DependencyClassifier

            classifier = DependencyClassifier()
            dep_classification = classifier.classify(self.prompt)
            self.dep_level = dep_classification.level
        except Exception:
            logger.warning("Dependency classifier unavailable — defaulting to standard cache", exc_info=True)

    # -- Phase 3: Cache lookup ---------------------------------------------

    async def _check_cache(self) -> Optional[GatewayResult]:
        """Check Redis exact / Pinecone semantic cache. Returns GatewayResult on hit."""
        # Build cache metadata for observability
        cache_metadata = {
            "bypass_requested": self.bypass_cache,
            "dependency_level": self.dep_level,
            "skip_reason": None,
            "cache_key_prefix": None,
            "semantic_similarity": None,
            "cache_age_seconds": 0,
        }

        # Explicit bypass requested (write-back loops, revision workflows, etc.)
        if self.bypass_cache:
            cache_metadata["skip_reason"] = "explicit_bypass"

            logger.info(
                "Cache bypassed via explicit flag",
                extra={
                    "org_id": self.org_id,
                    "agent_id": self.agent_id,
                    "bypass_cache": True,
                    "dependency_level": self.dep_level,
                }
            )

            # Track bypass metric
            try:
                from app.api.metrics import cache_bypasses_total
                cache_bypasses_total.labels(
                    org_id=self.org_id or "unknown",
                    reason="explicit_bypass"
                ).inc()
            except Exception:
                pass

            # Store metadata in instance for later use
            self._cache_metadata = cache_metadata
            return None

        # CRITICAL dependency classification always bypasses cache
        if self.dep_level and self.dep_level == "CRITICAL":
            cache_metadata["skip_reason"] = "critical_dependency"

            logger.info(
                "Cache bypassed for CRITICAL dependency",
                extra={
                    "org_id": self.org_id,
                    "agent_id": self.agent_id,
                    "dependency_level": "CRITICAL",
                }
            )

            # Track bypass metric
            try:
                from app.api.metrics import cache_bypasses_total
                cache_bypasses_total.labels(
                    org_id=self.org_id or "unknown",
                    reason="critical_dependency"
                ).inc()
            except Exception:
                pass

            # Store metadata in instance
            self._cache_metadata = cache_metadata
            return None

        if not (self.redis and self.org_id):
            return None
        try:
            from app.services.cache import RedisCache

            cache = RedisCache(self.redis)

            if self.dep_level is not None:
                from app.services.coherence_validator import CoherenceValidator

                validator = CoherenceValidator()
                hit = await cache.context_get(
                    self.org_id, self.prompt,
                    dependency_level=self.dep_level,
                    model=self.model_override,
                    coherence_validator=validator,
                )
            else:
                hit = await cache.get(self.org_id, self.prompt, model=self.model_override)

            if hit:
                elapsed = int((time.time() - self.start_time) * 1000)

                # Update cache metadata with hit details
                cache_metadata.update({
                    "skip_reason": None,
                    "cache_key_prefix": f"org:{self.org_id[:8]}" if self.org_id else "unknown",
                    "semantic_similarity": hit.similarity,
                    "cache_age_seconds": hit.cache_age_seconds if hasattr(hit, "cache_age_seconds") else 0,
                })

                logger.info(
                    "Cache HIT",
                    extra={
                        "org_id": self.org_id,
                        "agent_id": self.agent_id,
                        "cache_tier": hit.cache_tier,
                        "cache_hit": True,
                        "latency_ms": elapsed,
                        "similarity": hit.similarity or 1.0,
                        "cache_age_seconds": cache_metadata["cache_age_seconds"],
                    }
                )

                # Track cache hit metric
                try:
                    from app.api.metrics import cache_hits_total
                    cache_hits_total.labels(
                        org_id=self.org_id or "unknown",
                        tier=hit.cache_tier
                    ).inc()
                except Exception:
                    pass  # Don't fail request if metrics fail

                return GatewayResult(
                    response=hit.response,
                    model_used=hit.model_used,
                    model_requested=self.model_override,
                    provider=self.provider_hint,
                    routing_mode=self.normalized_routing_mode,
                    intervention_mode=self.norm_intervention_mode,
                    agent_id=self.agent_id,
                    agent_session_id=self.agent_session_id,
                    model_endpoint_id=self.model_endpoint_id,
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
                    policy_action="log",
                    policy_reason="Cache hit — intervention not applicable",
                    risk_score=self.risk_breakdown.composite_score if self.risk_breakdown else None,
                    risk_factors=self.risk_breakdown.factors if self.risk_breakdown else {},
                    intervention_level=0,
                    cache_metadata=cache_metadata,  # ← ADD DEBUG METADATA
                )
        except Exception as exc:
            logger.error(
                "Redis cache check failed",
                extra={
                    "org_id": self.org_id,
                    "agent_id": self.agent_id,
                    "error": str(exc),
                },
                exc_info=True
            )

        # Cache miss - log for debugging
        cache_metadata["skip_reason"] = "miss"

        logger.info(
            "Cache MISS",
            extra={
                "org_id": self.org_id,
                "agent_id": self.agent_id,
                "cache_hit": False,
                "dependency_level": self.dep_level,
                "prompt_length": len(self.prompt),
            }
        )

        # Track cache miss metric
        try:
            from app.api.metrics import cache_misses_total
            cache_misses_total.labels(
                org_id=self.org_id or "unknown",
                dependency_level=self.dep_level or "unknown"
            ).inc()
        except Exception:
            pass

        # Store metadata for later inclusion in response
        self._cache_metadata = cache_metadata
        return None

    # -- Phase 4: Intervention evaluation (sync, <0.5ms) -------------------

    def _evaluate_intervention(self) -> Optional[GatewayResult]:
        """Evaluate risk against intervention ladder. Returns GatewayResult if blocked."""
        if self.risk_breakdown is None:
            return None
        try:
            from app.services.intervention_engine import InterventionEngine

            intervention_eng = InterventionEngine()
            self.intervention_decision = intervention_eng.evaluate(
                risk_score=self.risk_breakdown.composite_score,
                intervention_mode=self.norm_intervention_mode,
                prompt=self.prompt,
                current_model=self.model_override,
                agent_type=self.agent_type,
                threshold_overrides=self.threshold_overrides,
            )

            if self.intervention_decision.should_block:
                elapsed = int((time.time() - self.start_time) * 1000)
                if self.org_id:
                    _fire_intervention_log(
                        org_id=self.org_id, agent_id=self.agent_id,
                        decision=self.intervention_decision,
                        risk_breakdown=self.risk_breakdown,
                        intervention_mode=self.norm_intervention_mode,
                        original_model=self.model_override, final_model=None,
                    )
                return GatewayResult(
                    response="",
                    routing_mode=self.normalized_routing_mode,
                    intervention_mode=self.norm_intervention_mode,
                    agent_id=self.agent_id,
                    agent_session_id=self.agent_session_id,
                    model_endpoint_id=self.model_endpoint_id,
                    latency_ms=elapsed,
                    policy_action="block",
                    policy_reason=self.intervention_decision.reason,
                    risk_score=self.risk_breakdown.composite_score,
                    risk_factors=self.risk_breakdown.factors,
                    intervention_level=self.intervention_decision.level.value,
                    error_message="Request blocked by intervention engine due to high risk score",
                )
        except Exception:
            logger.warning("Intervention engine unavailable — proceeding without intervention", exc_info=True)
        return None

    # -- Phase 5: Chain execution (GUIDED mode) ----------------------------

    async def _execute_chain(self) -> Optional[GatewayResult]:
        """Execute guided chain if chain_config is provided."""
        if not (self.chain_config and self.normalized_routing_mode == "GUIDED"):
            return None
        try:
            from src.providers import get_provider, EnvKeyResolver
            from src.providers.base import InferenceRequest as ProviderRequest
            from src.routing.guided_chain import (
                ChainSlotConfig,
                GuidedChainConfig,
                GuidedChainExecutor,
            )

            slots = [
                ChainSlotConfig(
                    position=s["position"],
                    model_id=s["model_id"],
                    provider=s["provider"],
                    fallback_triggers=self.chain_config.get("fallback_triggers", ["rate_limit", "server_error", "timeout"]),
                    max_latency_ms=s.get("max_latency_ms"),
                    max_cost_per_1k_tokens=s.get("max_cost_per_1k_tokens"),
                )
                for s in self.chain_config["slots"]
            ]
            guided_chain = GuidedChainConfig(
                chain_id=self.chain_config["chain_id"],
                name=self.chain_config["name"],
                slots=slots,
            )

            resolver = EnvKeyResolver()
            executor = GuidedChainExecutor(
                get_provider=get_provider,
                resolve_key=resolver.resolve,
            )

            request = ProviderRequest(model="", prompt=self.prompt, max_tokens=1024)

            chain_response, attempts = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: executor.execute(guided_chain, request, self.org_id),
            )

            elapsed = int((time.time() - self.start_time) * 1000)
            policy_action, policy_reason, i_level = self._resolve_policy_fields()
            r_score = self.risk_breakdown.composite_score if self.risk_breakdown else None
            r_factors = self.risk_breakdown.factors if self.risk_breakdown else {}

            return GatewayResult(
                response=chain_response.text,
                model_used=chain_response.model,
                model_requested=self.model_override,
                provider=chain_response.provider,
                routing_mode=self.normalized_routing_mode,
                intervention_mode=self.norm_intervention_mode,
                agent_id=self.agent_id,
                agent_session_id=self.agent_session_id,
                model_endpoint_id=self.model_endpoint_id,
                input_tokens=chain_response.input_tokens,
                output_tokens=chain_response.output_tokens,
                cost_without_asahi=0.0,
                cost_with_asahi=0.0,
                savings_usd=0.0,
                savings_pct=0.0,
                cache_hit=False,
                latency_ms=elapsed,
                routing_reason=f"Chain '{guided_chain.name}' executed ({len(attempts)} attempt(s))",
                routing_factors={
                    "chain_id": guided_chain.chain_id,
                    "attempts": [
                        {
                            "slot": a.slot_position,
                            "provider": a.provider,
                            "model": a.model,
                            "success": a.success,
                            "trigger": a.trigger,
                        }
                        for a in attempts
                    ],
                },
                policy_action=policy_action,
                policy_reason=policy_reason,
                risk_score=r_score,
                risk_factors=r_factors,
                intervention_level=i_level,
                cache_metadata=getattr(self, "_cache_metadata", None),
                routing_metadata={
                    "routing_mode": "GUIDED",
                    "chain_execution": True,
                    "chain_id": guided_chain.chain_id,
                    "chain_name": guided_chain.name,
                    "total_attempts": len(attempts),
                },
            )
        except Exception as exc:
            logger.warning("Chain execution failed, falling through to normal routing: %s", exc)
        return None

    # -- Phase 6+7: Route model selection + provider call ------------------

    async def _route_and_call_provider(self) -> GatewayResult:
        """Select model via routing engine and call the provider."""
        from app.services.provider_health import get_all_provider_health
        from app.services.routing import RoutingContext, RoutingEngine

        provider_health = get_all_provider_health()

        routing_ctx = RoutingContext(
            prompt=self.prompt,
            routing_mode=self.normalized_routing_mode,
            quality_preference=self.quality_preference or "high",
            latency_preference=self.latency_preference or "normal",
            model_override=self.model_override,
            provider_hint=self.provider_hint,
            provider_health=provider_health,
        )
        routing_engine = RoutingEngine()
        routing_decision = routing_engine.route(routing_ctx)

        effective_model = self.model_override or routing_decision.selected_model
        effective_prompt = self.prompt
        if self.intervention_decision is not None:
            if self.intervention_decision.rerouted_model:
                effective_model = self.intervention_decision.rerouted_model
            if self.intervention_decision.augmented_prompt:
                effective_prompt = self.intervention_decision.augmented_prompt

        optimizer = get_optimizer_instance(use_mock=self.use_mock)
        if not optimizer:
            return GatewayResult(
                response="Optimizer unavailable",
                error_message="Failed to initialize InferenceOptimizer",
            )

        selected_provider = routing_decision.selected_provider or self.provider_hint or "unknown"
        circuit = _get_circuit(selected_provider, self.redis)
        circuit.set_provider_health(provider_health.get(selected_provider, "healthy"))

        loop = asyncio.get_event_loop()
        try:
            async def _run():
                return await loop.run_in_executor(
                    None,
                    lambda: optimizer.infer(
                        prompt=effective_prompt,
                        routing_mode=_legacy_routing_mode(self.normalized_routing_mode),
                        quality_preference=self.quality_preference,
                        latency_preference=self.latency_preference,
                        model_override=effective_model,
                        organization_id=self.org_id,
                    ),
                )

            result = await execute_with_retry(
                _run, circuit, _PROVIDER_RETRY_CONFIG, timeout_seconds=30.0,
            )

            return self._build_response(result, routing_decision, selected_provider)

        except CircuitOpenError as exc:
            elapsed = int((time.time() - self.start_time) * 1000)
            logger.warning(
                "Circuit open for provider %s (org %s): %s",
                selected_provider, self.org_id, exc,
            )
            return GatewayResult(
                response="",
                routing_mode=self.normalized_routing_mode,
                intervention_mode=self.norm_intervention_mode,
                agent_id=self.agent_id,
                agent_session_id=self.agent_session_id,
                model_endpoint_id=self.model_endpoint_id,
                provider=selected_provider,
                latency_ms=elapsed,
                policy_action="circuit_open",
                policy_reason=f"Provider {selected_provider} temporarily unavailable",
                risk_score=self.risk_breakdown.composite_score if self.risk_breakdown else None,
                risk_factors=self.risk_breakdown.factors if self.risk_breakdown else {},
                intervention_level=0,
                error_message=f"Provider {selected_provider} temporarily unavailable — circuit breaker open",
            )
        except Exception as exc:
            logger.exception("Inference failed for org %s", self.org_id)
            return GatewayResult(response="", error_message=str(exc))

    # -- Phase 8: Build response + fire background tasks -------------------

    def _build_intervention_metadata(self) -> Optional[dict]:
        """Build intervention decision metadata for debugging.

        Returns metadata including:
        - intervention_mode: The mode used (OBSERVE/ASSISTED/AUTONOMOUS)
        - risk_score: Composite risk score
        - risk_factors: Breakdown of risk components
        - intervention_decision: Action taken and reasoning
        - prompt_changes: Original vs augmented prompt
        - model_changes: Original vs rerouted model
        """
        if not self.intervention_decision:
            return None

        metadata = {
            "intervention_mode": self.norm_intervention_mode,
            "risk_score": self.risk_breakdown.composite_score if self.risk_breakdown else None,
            "risk_factors": self.risk_breakdown.factors if self.risk_breakdown else {},
            "action": self.intervention_decision.action,
            "level": self.intervention_decision.level.value if self.intervention_decision.level else None,
            "reason": self.intervention_decision.reason,
            "should_block": self.intervention_decision.should_block,
        }

        # Prompt changes
        if self.intervention_decision.augmented_prompt:
            metadata["prompt_modified"] = True
            metadata["original_prompt_length"] = len(self.prompt)
            metadata["augmented_prompt_length"] = len(self.intervention_decision.augmented_prompt)
            # Don't include full prompts to avoid bloating response, but show they were modified
        else:
            metadata["prompt_modified"] = False

        # Model changes
        if self.intervention_decision.rerouted_model:
            metadata["model_rerouted"] = True
            metadata["original_model"] = self.model_override
            metadata["rerouted_model"] = self.intervention_decision.rerouted_model
        else:
            metadata["model_rerouted"] = False

        return metadata

    def _calculate_baseline_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost using baseline model (gpt-4-turbo) for comparison.

        This represents what the user would pay without ASAHIO's routing optimization.
        """
        try:
            from src.models.registry import get_model_config, calculate_cost
            baseline_model = get_model_config("gpt-4-turbo")
            if baseline_model:
                return calculate_cost(baseline_model, input_tokens, output_tokens)
        except Exception:
            pass

        # Fallback: use GPT-4 pricing directly ($0.01/1K input, $0.03/1K output)
        return ((input_tokens / 1000) * 0.01) + ((output_tokens / 1000) * 0.03)

    def _build_response(self, result, routing_decision, selected_provider: str) -> GatewayResult:
        """Assemble GatewayResult from provider response and fire background tasks."""
        elapsed = int((time.time() - self.start_time) * 1000)
        cache_tier_map = {0: None, 1: "exact", 2: "semantic", 3: "intermediate"}
        cache_tier = cache_tier_map.get(result.cache_tier, None)

        # Calculate real savings by comparing to baseline (gpt-4-turbo)
        cost_with = result.cost
        if result.cost_original:
            # Use provider-supplied baseline if available
            cost_original = result.cost_original
        else:
            # Calculate what it would cost with baseline model
            cost_original = self._calculate_baseline_cost(result.tokens_input, result.tokens_output)

        savings = cost_original - cost_with
        savings_pct = (savings / cost_original * 100) if cost_original > 0 else 0.0

        policy_action, policy_reason, i_level = self._resolve_policy_fields()
        r_score = self.risk_breakdown.composite_score if self.risk_breakdown else None
        r_factors = self.risk_breakdown.factors if self.risk_breakdown else {}
        i_metadata = self._build_intervention_metadata()

        # Classification and hallucination detection
        from app.services.classifiers import classify_agent_type, classify_output_type, estimate_complexity
        from app.services.hallucination_detector import HallucinationDetector

        agent_type = classify_agent_type(
            prompt=self.prompt,
            agent_name=getattr(self.agent, "name", None) if hasattr(self, "agent") else None,
            agent_metadata=getattr(self.agent, "metadata_", None) if hasattr(self, "agent") else None,
        )
        output_type = classify_output_type(result.response)
        complexity_score = estimate_complexity(
            prompt=self.prompt,
            response=result.response,
            input_tokens=result.tokens_input,
            output_tokens=result.tokens_output,
        )

        # Hallucination detection
        detector = HallucinationDetector(threshold=0.5)
        hallucination_result = detector.check(prompt=self.prompt, response=result.response)
        hallucination_detected = hallucination_result.detected

        gateway_result = GatewayResult(
            response=result.response,
            request_id=getattr(result, "request_id", None),
            model_used=result.model_used,
            model_requested=self.model_override,
            provider=routing_decision.selected_provider or self.provider_hint,
            routing_mode=self.normalized_routing_mode,
            intervention_mode=self.norm_intervention_mode,
            agent_id=self.agent_id,
            agent_session_id=self.agent_session_id,
            model_endpoint_id=self.model_endpoint_id,
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
            routing_metadata=routing_decision.metadata,
            policy_action=policy_action,
            policy_reason=policy_reason,
            risk_score=r_score,
            risk_factors=r_factors,
            intervention_level=i_level,
            intervention_metadata=i_metadata,
            cache_metadata=getattr(self, "_cache_metadata", None),
            # ABA / Model C classification fields
            agent_type=agent_type,
            complexity_score=complexity_score,
            output_type=output_type,
            hallucination_detected=hallucination_detected,
        )

        # Fire background tasks
        if self.redis and self.org_id and result.response and not result.cache_hit:
            # Enqueue cache storage with arq (retryable background task)
            try:
                from app.core.task_queue import enqueue_cache_storage

                asyncio.create_task(
                    enqueue_cache_storage(self.org_id, self.prompt, result.response, result.model_used)
                )
            except Exception as exc:
                logger.warning("Failed to enqueue cache storage, falling back to direct write: %s", exc)
                asyncio.create_task(
                    _store_in_cache(self.redis, self.org_id, self.prompt, result.response, result.model_used)
                )
        if self.org_id and self.intervention_decision is not None:
            _fire_intervention_log(
                org_id=self.org_id, agent_id=self.agent_id,
                decision=self.intervention_decision,
                risk_breakdown=self.risk_breakdown,
                intervention_mode=self.norm_intervention_mode,
                original_model=self.model_override,
                final_model=result.model_used,
            )

        return gateway_result

    # -- Helpers -----------------------------------------------------------

    def _resolve_policy_fields(self) -> tuple[str, str, int]:
        """Extract policy_action, policy_reason, intervention_level from decision."""
        if self.intervention_decision is not None:
            return (
                self.intervention_decision.action,
                self.intervention_decision.reason,
                self.intervention_decision.level.value,
            )
        return ("log", "Risk scorer unavailable — defaulting to log", 0)


# ---------------------------------------------------------------------------
# Public API — delegates to InferencePipeline
# ---------------------------------------------------------------------------

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
    session_step: Optional[int] = None,
    fingerprint_hallucination_rate: Optional[float] = None,
    agent_type: Optional[str] = None,
    threshold_overrides: Optional[dict] = None,
    chain_config: Optional[dict] = None,
    bypass_cache: bool = False,
) -> GatewayResult:
    pipeline = InferencePipeline(
        prompt=prompt,
        routing_mode=routing_mode,
        intervention_mode=intervention_mode,
        quality_preference=quality_preference,
        latency_preference=latency_preference,
        model_override=model_override,
        org_id=org_id,
        agent_id=agent_id,
        agent_session_id=agent_session_id,
        model_endpoint_id=model_endpoint_id,
        provider_hint=provider_hint,
        use_mock=use_mock,
        redis=redis,
        session_step=session_step,
        fingerprint_hallucination_rate=fingerprint_hallucination_rate,
        agent_type=agent_type,
        threshold_overrides=threshold_overrides,
        chain_config=chain_config,
        bypass_cache=bypass_cache,
    )
    return await pipeline.execute()


# ---------------------------------------------------------------------------
# Background helpers
# ---------------------------------------------------------------------------

async def _store_in_cache(redis, org_id: str, query: str, response: str, model_used: str) -> None:
    try:
        from app.services.cache import RedisCache

        cache = RedisCache(redis)
        await cache.set(org_id, query, response, model_used)
    except Exception:
        logger.exception("Failed to cache result for org %s", org_id)


def _fire_intervention_log(
    *,
    org_id: str,
    agent_id: Optional[str],
    decision,
    risk_breakdown,
    intervention_mode: str,
    original_model: Optional[str],
    final_model: Optional[str],
) -> None:
    """Fire-and-forget intervention log write."""
    try:
        from app.services.intervention_writer import (
            InterventionLogPayload,
            write_intervention_log,
        )

        payload = InterventionLogPayload(
            org_id=org_id,
            agent_id=agent_id,
            intervention_level=decision.level.value,
            intervention_mode=intervention_mode,
            risk_score=risk_breakdown.composite_score if risk_breakdown else 0.0,
            risk_factors=risk_breakdown.factors if risk_breakdown else {},
            action_taken=decision.action,
            action_detail=decision.reason,
            original_model=original_model,
            final_model=final_model,
            prompt_modified=decision.augmented_prompt is not None,
            was_blocked=decision.should_block,
        )
        asyncio.create_task(write_intervention_log(payload))
    except Exception:
        logger.warning("Failed to fire intervention log task", exc_info=True)

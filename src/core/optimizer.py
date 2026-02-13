"""
Core inference optimizer for Asahi.

Orchestrates caching, routing, inference execution, cost tracking,
and event logging to minimize inference costs while meeting quality
and latency constraints.
"""

import logging
import os
import random
import time
import uuid
from typing import List, Literal, Optional, Tuple

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from src.cache.exact import Cache, CacheEntry
from src.cache.intermediate import IntermediateCache
from src.cache.semantic import SemanticCache, SemanticCacheResult
from src.cache.workflow import WorkflowDecomposer, WorkflowStep
from src.config import get_settings
from src.embeddings.engine import EmbeddingEngine, EmbeddingConfig
from src.embeddings.mismatch import MismatchCostCalculator
from src.embeddings.similarity import SimilarityCalculator
from src.embeddings.threshold import AdaptiveThresholdTuner
from src.embeddings.vector_store import InMemoryVectorDB, VectorDatabase
from src.exceptions import ModelNotFoundError, ProviderError
from src.models.registry import (
    ModelProfile,
    ModelRegistry,
    calculate_cost,
    estimate_tokens,
)
from src.routing.constraints import (
    ConstraintInterpreter,
    RoutingConstraints,
    RoutingDecision,
)
from src.routing.router import AdvancedRouter, AdvancedRoutingDecision, Router, RoutingMode
from src.routing.task_detector import TaskTypeDetector
from src.tracking.tracker import EventTracker, InferenceEvent

load_dotenv()

logger = logging.getLogger(__name__)


class InferenceResult(BaseModel):
    """Structured result of an inference request.

    Attributes:
        response: The LLM response text.
        model_used: Selected model name.
        tokens_input: Actual input token count.
        tokens_output: Actual output token count.
        cost: Dollar cost for this request.
        latency_ms: End-to-end latency in milliseconds.
        cache_hit: Whether the result came from cache.
        routing_reason: Explanation of model choice.
        request_id: UUID for tracing.
    """

    response: str = ""
    model_used: str = ""
    tokens_input: int = 0
    tokens_output: int = 0
    cost: float = 0.0
    latency_ms: float = 0.0
    cache_hit: bool = False
    routing_reason: str = ""
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])


class InferenceOptimizer:
    """Central orchestrator for the Asahi inference pipeline.

    Owns the complete request lifecycle: cache check, routing,
    inference execution, cost calculation, event logging, and
    response assembly.

    Supports three-tier caching (exact match, semantic similarity,
    intermediate results) and advanced routing modes (AUTOPILOT,
    GUIDED, EXPLICIT).

    Args:
        registry: Model registry (injected).
        router: Basic routing engine (injected, optional if advanced_router provided).
        cache: Exact-match cache (Tier 1, injected).
        tracker: Event tracker (injected).
        use_mock: If ``True``, simulate API calls instead of calling
            real providers.
        semantic_cache: Tier 2 semantic cache (optional).
        intermediate_cache: Tier 3 intermediate cache (optional).
        workflow_decomposer: Workflow decomposer for Tier 3 (optional).
        advanced_router: Advanced router with 3 modes (optional).
        task_detector: Task type detector (optional, auto-initialized if advanced_router used).
        constraint_interpreter: Constraint interpreter (optional, auto-initialized if advanced_router used).
        enable_tier2: Enable Tier 2 semantic caching (default: True if semantic_cache provided).
        enable_tier3: Enable Tier 3 intermediate caching (default: True if components provided).
    """

    def __init__(
        self,
        registry: Optional[ModelRegistry] = None,
        router: Optional[Router] = None,
        cache: Optional[Cache] = None,
        tracker: Optional[EventTracker] = None,
        use_mock: bool = False,
        semantic_cache: Optional[SemanticCache] = None,
        intermediate_cache: Optional[IntermediateCache] = None,
        workflow_decomposer: Optional[WorkflowDecomposer] = None,
        advanced_router: Optional[AdvancedRouter] = None,
        task_detector: Optional[TaskTypeDetector] = None,
        constraint_interpreter: Optional[ConstraintInterpreter] = None,
        enable_tier2: Optional[bool] = None,
        enable_tier3: Optional[bool] = None,
    ) -> None:
        self._registry = registry or ModelRegistry()
        self._cache = cache or Cache()
        self._tracker = tracker or EventTracker()
        self._use_mock = use_mock
        self._start_time = time.time()

        # Phase 1 components
        self._router = router or Router(self._registry)

        # Phase 2 components (optional)
        self._semantic_cache = semantic_cache
        self._intermediate_cache = intermediate_cache
        self._workflow_decomposer = workflow_decomposer
        self._advanced_router = advanced_router
        self._task_detector = task_detector
        self._constraint_interpreter = constraint_interpreter

        # Feature flags (auto-detect from component availability)
        self._enable_tier2 = (
            enable_tier2
            if enable_tier2 is not None
            else (self._semantic_cache is not None)
        )
        self._enable_tier3 = (
            enable_tier3
            if enable_tier3 is not None
            else (
                self._intermediate_cache is not None
                and self._workflow_decomposer is not None
            )
        )

        # Lazy initialization helpers
        self._phase2_initialized = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def infer(
        self,
        prompt: str,
        task_id: Optional[str] = None,
        latency_budget_ms: Optional[int] = None,
        quality_threshold: Optional[float] = None,
        cost_budget: Optional[float] = None,
        user_id: Optional[str] = None,
        routing_mode: RoutingMode = "autopilot",
        quality_preference: Optional[str] = None,
        latency_preference: Optional[str] = None,
        model_override: Optional[str] = None,
        document_id: Optional[str] = None,
    ) -> InferenceResult:
        """Run a full inference request through the optimization pipeline.

        Supports three-tier caching and advanced routing modes.

        Args:
            prompt: The user query.
            task_id: Optional task identifier for tracking.
            latency_budget_ms: Maximum acceptable latency.
            quality_threshold: Minimum quality score (0.0-5.0).
            cost_budget: Optional maximum dollar cost for this request.
            user_id: Optional caller identity.
            routing_mode: Routing mode: "autopilot", "guided", or "explicit".
            quality_preference: Quality preference for GUIDED mode ("low", "medium", "high", "max").
            latency_preference: Latency preference for GUIDED mode ("low", "medium", "high").
            model_override: Model name for EXPLICIT mode.
            document_id: Optional document identifier for Tier 3 workflow decomposition.

        Returns:
            InferenceResult with response, cost, and metadata.
        """
        _s = get_settings().routing
        if latency_budget_ms is None:
            latency_budget_ms = _s.default_latency_budget_ms
        if quality_threshold is None:
            quality_threshold = _s.default_quality_threshold

        request_id = uuid.uuid4().hex[:12]

        if not prompt or not prompt.strip():
            logger.warning(
                "Empty prompt received",
                extra={"request_id": request_id},
            )
            return InferenceResult(
                request_id=request_id,
                routing_reason="Error: empty prompt",
            )

        # 1. TIER 1: Exact match cache
        cache_entry = self._check_cache(prompt)
        if cache_entry is not None:
            result = InferenceResult(
                response=cache_entry.response,
                model_used=cache_entry.model,
                tokens_input=0,
                tokens_output=0,
                cost=0.0,
                latency_ms=0.0,
                cache_hit=True,
                routing_reason="Cache hit (exact match)",
                request_id=request_id,
            )
            self._log_event(
                request_id=request_id,
                event_model=cache_entry.model,
                cache_hit=True,
                input_tokens=0,
                output_tokens=0,
                latency_ms=0,
                cost=0.0,
                routing_reason="Cache hit (Tier 1)",
                task_type=task_id,
                user_id=user_id,
            )
            return result

        # 2. TIER 2: Semantic similarity cache
        if self._enable_tier2 and self._semantic_cache is not None:
            try:
                detected_task = task_id or self._detect_task_type(prompt)
                estimated_cost = self._estimate_recompute_cost(
                    prompt, quality_threshold
                )
                # Use "high" cost_sensitivity for more aggressive caching
                # This lowers the threshold, allowing semantically similar queries to match
                semantic_result = self._semantic_cache.get(
                    query=prompt,
                    task_type=detected_task,
                    cost_sensitivity="high",  # Changed from "medium" to "high" for more aggressive caching
                    recompute_cost=estimated_cost,
                )
                if semantic_result.hit:
                    result = InferenceResult(
                        response=semantic_result.response or "",
                        model_used="cached",
                        tokens_input=0,
                        tokens_output=0,
                        cost=0.0,
                        latency_ms=0.0,
                        cache_hit=True,
                        routing_reason=(
                            f"Cache hit (semantic similarity: "
                            f"{semantic_result.similarity:.2f})"
                        ),
                        request_id=request_id,
                    )
                    self._log_event(
                        request_id=request_id,
                        event_model="cached",
                        cache_hit=True,
                        input_tokens=0,
                        output_tokens=0,
                        latency_ms=0,
                        cost=0.0,
                        routing_reason="Cache hit (Tier 2)",
                        task_type=detected_task,
                        user_id=user_id,
                    )
                    return result
            except Exception as exc:
                logger.warning(
                    "Tier 2 cache check failed, continuing",
                    extra={"request_id": request_id, "error": str(exc)},
                )

        # 3. TIER 3: Intermediate result cache (optional)
        workflow_steps: Optional[List[WorkflowStep]] = None
        if self._enable_tier3 and self._workflow_decomposer is not None:
            try:
                workflow_steps = self._workflow_decomposer.decompose(
                    prompt=prompt,
                    document_id=document_id,
                    task_type=task_id,
                )
                # Check if all steps can be served from intermediate cache
                if workflow_steps and self._intermediate_cache is not None:
                    all_hit = True
                    combined_result_parts = []
                    for step in workflow_steps:
                        cached_result = self._intermediate_cache.get(step.cache_key)
                        if cached_result:
                            combined_result_parts.append(cached_result)
                        else:
                            all_hit = False
                            break

                    if all_hit and combined_result_parts:
                        combined_response = " ".join(combined_result_parts)
                        result = InferenceResult(
                            response=combined_response,
                            model_used="cached",
                            tokens_input=0,
                            tokens_output=0,
                            cost=0.0,
                            latency_ms=0.0,
                            cache_hit=True,
                            routing_reason="Cache hit (intermediate results)",
                            request_id=request_id,
                        )
                        self._log_event(
                            request_id=request_id,
                            event_model="cached",
                            cache_hit=True,
                            input_tokens=0,
                            output_tokens=0,
                            latency_ms=0,
                            cost=0.0,
                            routing_reason="Cache hit (Tier 3)",
                            task_type=task_id,
                            user_id=user_id,
                        )
                        return result
            except Exception as exc:
                logger.warning(
                    "Tier 3 cache check failed, continuing",
                    extra={"request_id": request_id, "error": str(exc)},
                )

        # 4. ROUTE: Use AdvancedRouter if available, otherwise basic Router
        if self._advanced_router is not None:
            decision = self._route_advanced(
                prompt=prompt,
                mode=routing_mode,
                quality_preference=quality_preference,
                latency_preference=latency_preference,
                model_override=model_override,
                quality_threshold=quality_threshold,
                latency_budget_ms=latency_budget_ms,
                cost_budget=cost_budget,
            )
        else:
            constraints = RoutingConstraints(
                quality_threshold=quality_threshold,
                latency_budget_ms=latency_budget_ms,
                cost_budget=cost_budget,
            )
            decision = self._route(constraints)

        # 3. EXECUTE INFERENCE
        start = time.time()
        try:
            response_text, actual_input, actual_output, provider_latency = (
                self._execute_inference(decision.model_name, prompt)
            )
        except ProviderError:
            logger.warning(
                "Primary model failed, attempting fallback",
                extra={
                    "request_id": request_id,
                    "failed_model": decision.model_name,
                },
            )
            fallback_model = max(
                self._registry.all(), key=lambda m: m.quality_score
            )
            if fallback_model.name == decision.model_name:
                raise
            response_text, actual_input, actual_output, provider_latency = (
                self._execute_inference(fallback_model.name, prompt)
            )
            decision = RoutingDecision(
                model_name=fallback_model.name,
                reason=f"Fallback after {decision.model_name} failed",
                fallback_used=True,
            )

        total_latency_ms = (time.time() - start) * 1000

        # 4. CALCULATE COST
        model_profile = self._registry.get(decision.model_name)
        cost = calculate_cost(model_profile, actual_input, actual_output)

        # 5. STORE IN ALL CACHE TIERS
        # Tier 1: Exact match
        self._cache.set(
            query=prompt,
            response=response_text,
            model=decision.model_name,
            cost=cost,
        )

        # Tier 2: Semantic cache
        if self._enable_tier2 and self._semantic_cache is not None:
            try:
                detected_task = task_id or self._detect_task_type(prompt)
                self._semantic_cache.set(
                    query=prompt,
                    response=response_text,
                    model=decision.model_name,
                    cost=cost,
                    task_type=detected_task,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to store in Tier 2 cache",
                    extra={"request_id": request_id, "error": str(exc)},
                )

        # Tier 3: Intermediate cache (if workflow was decomposed)
        if (
            self._enable_tier3
            and workflow_steps
            and self._intermediate_cache is not None
        ):
            try:
                # Store intermediate results for each step
                # (In a real implementation, we'd execute the workflow and cache each step)
                # For now, we'll cache the final result with the step keys
                for step in workflow_steps:
                    self._intermediate_cache.set(
                        cache_key=step.cache_key,
                        result=response_text,  # Simplified: store full response per step
                        metadata={"step_type": step.step_type, "step_id": step.step_id},
                    )
            except Exception as exc:
                logger.warning(
                    "Failed to store in Tier 3 cache",
                    extra={"request_id": request_id, "error": str(exc)},
                )

        # 6. LOG EVENT
        self._log_event(
            request_id=request_id,
            event_model=decision.model_name,
            cache_hit=False,
            input_tokens=actual_input,
            output_tokens=actual_output,
            latency_ms=int(total_latency_ms),
            cost=cost,
            routing_reason=decision.reason,
            task_type=task_id,
            user_id=user_id,
        )

        # 7. RETURN
        return InferenceResult(
            response=response_text,
            model_used=decision.model_name,
            tokens_input=actual_input,
            tokens_output=actual_output,
            cost=cost,
            latency_ms=round(total_latency_ms, 1),
            cache_hit=False,
            routing_reason=decision.reason,
            request_id=request_id,
        )

    def get_metrics(self) -> dict:
        """Return current metrics summary including cache and uptime.

        Returns:
            Dict with analytics from the tracker plus cache stats.
        """
        summary = self._tracker.get_metrics()
        cache_stats = self._cache.stats()
        summary["cache_size"] = cache_stats.entry_count
        summary["cache_hit_rate"] = round(cache_stats.hit_rate, 4)
        summary["cache_cost_saved"] = cache_stats.total_cost_saved
        summary["uptime_seconds"] = round(time.time() - self._start_time, 1)
        return summary

    # ------------------------------------------------------------------
    # Properties for external access to components
    # ------------------------------------------------------------------

    @property
    def registry(self) -> ModelRegistry:
        """Access the model registry."""
        return self._registry

    @property
    def cache(self) -> Cache:
        """Access the cache."""
        return self._cache

    @property
    def tracker(self) -> EventTracker:
        """Access the event tracker."""
        return self._tracker

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_cache(self, prompt: str) -> Optional[CacheEntry]:
        """Delegate cache lookup to the cache component."""
        return self._cache.get(prompt)

    def _route(self, constraints: RoutingConstraints) -> RoutingDecision:
        """Delegate model selection to the basic router."""
        return self._router.select_model(constraints)

    def _route_advanced(
        self,
        prompt: str,
        mode: RoutingMode,
        quality_preference: Optional[str],
        latency_preference: Optional[str],
        model_override: Optional[str],
        quality_threshold: Optional[float],
        latency_budget_ms: Optional[int],
        cost_budget: Optional[float],
    ) -> RoutingDecision:
        """Route using AdvancedRouter and convert to RoutingDecision."""
        if self._advanced_router is None:
            # Fallback to basic router
            constraints = RoutingConstraints(
                quality_threshold=quality_threshold or 3.5,
                latency_budget_ms=latency_budget_ms or 300,
                cost_budget=cost_budget,
            )
            return self._router.select_model(constraints)

        advanced_decision = self._advanced_router.route(
            prompt=prompt,
            mode=mode,
            quality_preference=quality_preference,
            latency_preference=latency_preference,
            model_override=model_override,
        )

        # Convert AdvancedRoutingDecision to RoutingDecision
        return RoutingDecision(
            model_name=advanced_decision.model_name,
            reason=advanced_decision.reason,
            score=advanced_decision.score,
        )

    def _detect_task_type(self, prompt: str) -> str:
        """Detect task type from prompt using TaskTypeDetector if available."""
        if self._task_detector is not None:
            try:
                detection = self._task_detector.detect(prompt)
                return detection.task_type
            except Exception as exc:
                logger.warning(
                    "Task type detection failed",
                    extra={"error": str(exc)},
                )
        return "general"

    def _estimate_recompute_cost(
        self, prompt: str, quality_threshold: Optional[float]
    ) -> float:
        """Estimate the cost of recomputing this inference."""
        # Use a default model that meets the quality threshold
        if quality_threshold:
            candidates = [
                m
                for m in self._registry.all()
                if m.quality_score >= quality_threshold
            ]
            if candidates:
                model = min(candidates, key=lambda m: m.quality_score)
            else:
                model = max(self._registry.all(), key=lambda m: m.quality_score)
        else:
            model = max(self._registry.all(), key=lambda m: m.quality_score)

        input_tokens = estimate_tokens(prompt)
        output_tokens = max(20, int(input_tokens * 0.6))  # Estimate output
        return calculate_cost(model, input_tokens, output_tokens)

    def _execute_inference(
        self, model_name: str, prompt: str
    ) -> Tuple[str, int, int, int]:
        """Call the provider API or mock, with retry logic.

        Args:
            model_name: Which model to call.
            prompt: The user query.

        Returns:
            Tuple of (response_text, input_tokens, output_tokens, latency_ms).

        Raises:
            ProviderError: After all retries are exhausted.
        """
        if self._use_mock:
            return self._mock_call(model_name, prompt)

        profile = self._registry.get(model_name)

        last_error: Optional[Exception] = None
        for attempt in range(3):
            try:
                if profile.provider == "openai":
                    return self._call_openai(model_name, prompt)
                elif profile.provider == "anthropic":
                    return self._call_anthropic(model_name, prompt)
                else:
                    raise ProviderError(
                        f"Unknown provider: {profile.provider}"
                    )
            except ProviderError:
                raise
            except Exception as exc:
                last_error = exc
                wait = 2**attempt
                logger.warning(
                    "Provider call failed, retrying",
                    extra={
                        "model": model_name,
                        "attempt": attempt + 1,
                        "wait_seconds": wait,
                        "error": str(exc),
                    },
                )
                if attempt < 2:
                    time.sleep(wait)

        raise ProviderError(
            f"Failed after 3 retries for {model_name}: {last_error}"
        )

    def _call_openai(
        self, model_name: str, prompt: str
    ) -> Tuple[str, int, int, int]:
        """Call the OpenAI API."""
        from openai import OpenAI

        start = time.time()
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
        )
        latency_ms = int((time.time() - start) * 1000)
        text = response.choices[0].message.content or ""
        input_tokens = (
            response.usage.prompt_tokens if response.usage else estimate_tokens(prompt)
        )
        output_tokens = (
            response.usage.completion_tokens
            if response.usage
            else estimate_tokens(text)
        )
        return text, input_tokens, output_tokens, latency_ms

    def _call_anthropic(
        self, model_name: str, prompt: str
    ) -> Tuple[str, int, int, int]:
        """Call the Anthropic API."""
        import anthropic

        start = time.time()
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        response = client.messages.create(
            model=model_name,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        latency_ms = int((time.time() - start) * 1000)
        text = response.content[0].text if response.content else ""
        input_tokens = (
            response.usage.input_tokens
            if response.usage
            else estimate_tokens(prompt)
        )
        output_tokens = (
            response.usage.output_tokens
            if response.usage
            else estimate_tokens(text)
        )
        return text, input_tokens, output_tokens, latency_ms

    def _mock_call(
        self, model_name: str, prompt: str
    ) -> Tuple[str, int, int, int]:
        """Simulate an API call with realistic latency and token counts."""
        profile = self._registry.get(model_name)
        base_latency = profile.avg_latency_ms / 1000
        jitter = random.uniform(0.8, 1.2)
        time.sleep(base_latency * jitter * 0.01)

        input_tokens = estimate_tokens(prompt)
        output_tokens = max(20, int(input_tokens * random.uniform(0.3, 0.8)))
        latency_ms = int(profile.avg_latency_ms * jitter)

        response_text = (
            f"[Mock response from {model_name}] "
            f"Processed prompt with {input_tokens} input tokens. "
            f"This is a simulated response for testing purposes."
        )
        return response_text, input_tokens, output_tokens, latency_ms

    def _log_event(
        self,
        request_id: str,
        event_model: str,
        cache_hit: bool,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
        cost: float,
        routing_reason: str,
        task_type: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> None:
        """Create and log an InferenceEvent."""
        event = InferenceEvent(
            request_id=request_id,
            model_selected=event_model,
            cache_hit=cache_hit,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            latency_ms=latency_ms,
            cost=cost,
            routing_reason=routing_reason,
            task_type=task_type,
            user_id=user_id,
        )
        self._tracker.log_event(event)

    def _calculate_cost(
        self, model_name: str, input_tokens: int, output_tokens: int
    ) -> float:
        """Calculate cost using the registry."""
        try:
            profile = self._registry.get(model_name)
            return calculate_cost(profile, input_tokens, output_tokens)
        except ModelNotFoundError:
            logger.error(
                "Model not in registry for cost calculation",
                extra={"model": model_name},
            )
            return 0.0

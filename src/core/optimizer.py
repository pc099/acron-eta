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
from typing import Optional, Tuple

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from src.cache.exact import Cache, CacheEntry
from src.exceptions import ModelNotFoundError, ProviderError
from src.models.registry import (
    ModelProfile,
    ModelRegistry,
    calculate_cost,
    estimate_tokens,
)
from src.routing.constraints import RoutingConstraints, RoutingDecision
from src.routing.router import Router
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

    Args:
        registry: Model registry (injected).
        router: Routing engine (injected).
        cache: Exact-match cache (injected).
        tracker: Event tracker (injected).
        use_mock: If ``True``, simulate API calls instead of calling
            real providers.
    """

    def __init__(
        self,
        registry: Optional[ModelRegistry] = None,
        router: Optional[Router] = None,
        cache: Optional[Cache] = None,
        tracker: Optional[EventTracker] = None,
        use_mock: bool = False,
    ) -> None:
        self._registry = registry or ModelRegistry()
        self._router = router or Router(self._registry)
        self._cache = cache or Cache()
        self._tracker = tracker or EventTracker()
        self._use_mock = use_mock
        self._start_time = time.time()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def infer(
        self,
        prompt: str,
        task_id: Optional[str] = None,
        latency_budget_ms: int = 300,
        quality_threshold: float = 3.5,
        cost_budget: Optional[float] = None,
        user_id: Optional[str] = None,
    ) -> InferenceResult:
        """Run a full inference request through the optimization pipeline.

        Args:
            prompt: The user query.
            task_id: Optional task identifier for tracking.
            latency_budget_ms: Maximum acceptable latency.
            quality_threshold: Minimum quality score (0.0-5.0).
            cost_budget: Optional maximum dollar cost for this request.
            user_id: Optional caller identity.

        Returns:
            InferenceResult with response, cost, and metadata.
        """
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

        # 1. CACHE CHECK
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
                routing_reason="Cache hit",
                task_type=task_id,
                user_id=user_id,
            )
            return result

        # 2. ROUTE
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

        # 5. CACHE RESULT
        self._cache.set(
            query=prompt,
            response=response_text,
            model=decision.model_name,
            cost=cost,
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
        """Delegate model selection to the router."""
        return self._router.select_model(constraints)

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

"""
Core inference optimizer for Asahi.

Orchestrates caching, routing, inference execution, cost tracking,
and event logging to minimize inference costs while meeting quality
and latency constraints.
"""

import logging
import os
import random
import threading
import time
import uuid
from concurrent.futures import Future
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple

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
from src.exceptions import (
    BudgetExceededError,
    ModelNotFoundError,
    PermissionDeniedError,
    ProviderError,
)
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

# Optional: batching queue (Step 5 full batching)
try:
    from src.batching.queue import QueuedRequest, RequestQueue
except ImportError:
    QueuedRequest = None  # type: ignore[misc, assignment]
    RequestQueue = None  # type: ignore[misc, assignment]

# Optional: token optimization and feature enrichment (Steps 3 & 4)
try:
    from src.features.enricher import EnrichmentResult, FeatureEnricher
    from src.optimization.optimizer import OptimizationResult, TokenOptimizer
except ImportError:
    FeatureEnricher = None  # type: ignore[misc, assignment]
    TokenOptimizer = None  # type: ignore[misc, assignment]
    EnrichmentResult = None  # type: ignore[misc, assignment]
    OptimizationResult = None  # type: ignore[misc, assignment]

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
        cache_tier: Cache tier that served (1, 2, 3) or 0 for miss.
        routing_reason: Explanation of model choice.
        request_id: UUID for tracing.
        cost_original: Optional baseline cost for dashboard.
        cost_savings_percent: Optional percent saved for dashboard.
        optimization_techniques: Optional list of techniques applied.
    """

    response: str = ""
    model_used: str = ""
    tokens_input: int = 0
    tokens_output: int = 0
    cost: float = 0.0
    latency_ms: float = 0.0
    cache_hit: bool = False
    cache_tier: int = Field(default=0, ge=0, le=3)
    routing_reason: str = ""
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    cost_original: Optional[float] = None
    cost_savings_percent: Optional[float] = None
    optimization_techniques: Optional[List[str]] = None


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
        token_optimizer: Optional token optimizer (Step 3); reduces prompt tokens before inference.
        feature_enricher: Optional feature enricher (Step 4); adds user/org context to prompt.
        batch_engine: Optional batch engine (Step 5); evaluates batch eligibility.
        request_queue: Optional queue for batching; when set with batch_scheduler, eligible requests are enqueued.
        batch_scheduler: Optional scheduler; must be started by the app when request_queue is used.
        governance_engine: Optional governance engine (Step 6); enforces policy and budget when org_id is set.
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
        token_optimizer: Optional[Any] = None,
        feature_enricher: Optional[Any] = None,
        batch_engine: Optional[Any] = None,
        request_queue: Optional[Any] = None,
        batch_scheduler: Optional[Any] = None,
        governance_engine: Optional[Any] = None,
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

        # Step 3, 4, 5 (optional)
        self._token_optimizer = token_optimizer
        self._feature_enricher = feature_enricher
        self._batch_engine = batch_engine
        self._request_queue = request_queue
        self._batch_scheduler = batch_scheduler
        self._governance_engine = governance_engine

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
        # Connection pooling: one client per provider per process (thread-safe lazy init)
        self._openai_client: Any = None
        self._anthropic_client: Any = None
        self._provider_lock = threading.Lock()

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
        organization_id: Optional[str] = None,
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
            organization_id: Optional organisation ID (for feature enrichment).
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

        # 1. TIER 1: Exact match cache (org-scoped when organization_id present)
        cache_entry = self._check_cache(prompt, organization_id)
        if cache_entry is not None:
            result = InferenceResult(
                response=cache_entry.response,
                model_used=cache_entry.model,
                tokens_input=0,
                tokens_output=0,
                cost=0.0,
                latency_ms=0.0,
                cache_hit=True,
                cache_tier=1,
                routing_reason="Cache hit (exact match)",
                request_id=request_id,
                optimization_techniques=["cache_tier_1"],
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
                organization_id=organization_id,
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
                        cache_tier=2,
                        routing_reason=(
                            f"Cache hit (semantic similarity: "
                            f"{semantic_result.similarity:.2f})"
                        ),
                        request_id=request_id,
                        optimization_techniques=["semantic_cache"],
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
                        organization_id=organization_id,
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
                            cache_tier=3,
                            routing_reason="Cache hit (intermediate results)",
                            request_id=request_id,
                            optimization_techniques=["cache_tier_3"],
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
                            organization_id=organization_id,
                        )
                        return result
            except Exception as exc:
                logger.warning(
                    "Tier 3 cache check failed, continuing",
                    extra={"request_id": request_id, "error": str(exc)},
                )

        # 3a. FEATURE ENRICHMENT (Step 4): add user/org context when IDs present
        prompt_to_use = prompt
        if self._feature_enricher is not None and (user_id or organization_id):
            try:
                enrichment_result = self._feature_enricher.enrich(
                    prompt=prompt,
                    user_id=user_id,
                    organization_id=organization_id,
                    task_type=task_id or "general",
                )
                if enrichment_result.features_available:
                    prompt_to_use = enrichment_result.enriched_prompt
                    logger.debug(
                        "Prompt enriched",
                        extra={
                            "request_id": request_id,
                            "features_used": len(enrichment_result.features_used),
                        },
                    )
            except Exception as exc:
                logger.warning(
                    "Feature enrichment failed, using original prompt",
                    extra={"request_id": request_id, "error": str(exc)},
                )

        # 3b. TOKEN OPTIMIZATION (Step 3): reduce prompt tokens when safe
        if self._token_optimizer is not None:
            try:
                opt_settings = get_settings().optimization
                opt_result = self._token_optimizer.optimize(
                    prompt=prompt_to_use,
                    system_prompt=None,
                    history=None,
                    examples=None,
                    task_type=task_id or "general",
                    quality_preference=quality_preference or "medium",
                )
                risk_order = {"none": 0, "low": 1, "medium": 2, "high": 3}
                max_risk = risk_order.get(opt_settings.max_quality_risk, 2)
                result_risk = risk_order.get(opt_result.quality_risk, 0)
                if result_risk <= max_risk and opt_result.optimized_prompt:
                    prompt_to_use = opt_result.optimized_prompt
                    logger.debug(
                        "Prompt token-optimized",
                        extra={
                            "request_id": request_id,
                            "tokens_saved": opt_result.tokens_saved,
                        },
                    )
                elif result_risk > max_risk:
                    logger.debug(
                        "Token optimization skipped (quality risk too high)",
                        extra={
                            "request_id": request_id,
                            "quality_risk": opt_result.quality_risk,
                        },
                    )
            except Exception as exc:
                logger.warning(
                    "Token optimization failed, using current prompt",
                    extra={"request_id": request_id, "error": str(exc)},
                )

        # 4. ROUTE: Use AdvancedRouter if available, otherwise basic Router
        if self._advanced_router is not None:
            decision = self._route_advanced(
                prompt=prompt_to_use,
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

        # 4b. BATCH ELIGIBILITY (Step 5): enqueue and wait, or fall through to execute
        if (
            self._batch_engine is not None
            and self._request_queue is not None
            and QueuedRequest is not None
        ):
            try:
                eligibility = self._batch_engine.evaluate(
                    prompt=prompt_to_use,
                    task_type=task_id or "general",
                    model=decision.model_name,
                    latency_budget_ms=latency_budget_ms or 60_000,
                )
                if eligibility.eligible and eligibility.batch_group and eligibility.max_wait_ms is not None:
                    infer_kwargs: Dict[str, Any] = {
                        "prompt": prompt_to_use,
                        "task_id": task_id,
                        "latency_budget_ms": latency_budget_ms,
                        "quality_threshold": quality_threshold,
                        "cost_budget": cost_budget,
                        "user_id": user_id,
                        "organization_id": organization_id,
                        "routing_mode": routing_mode,
                        "quality_preference": quality_preference,
                        "latency_preference": latency_preference,
                        "model_override": decision.model_name,
                        "document_id": document_id,
                    }
                    fut: Future[InferenceResult] = Future()
                    deadline = datetime.now(timezone.utc) + timedelta(
                        milliseconds=eligibility.max_wait_ms
                    )
                    qr = QueuedRequest(
                        request_id=request_id,
                        prompt=prompt_to_use,
                        model=decision.model_name,
                        batch_group=eligibility.batch_group,
                        deadline=deadline,
                        future=fut,
                        infer_kwargs=infer_kwargs,
                    )
                    self._request_queue.enqueue(qr)
                    timeout_sec = (eligibility.max_wait_ms / 1000.0) + 2.0
                    try:
                        batch_result = fut.result(timeout=timeout_sec)
                        return batch_result
                    except Exception:
                        self._request_queue.remove(request_id)
                        logger.debug(
                            "Batch wait timed out or failed, executing individually",
                            extra={"request_id": request_id},
                        )
            except Exception as exc:
                logger.debug(
                    "Batch eligibility or enqueue skipped",
                    extra={"request_id": request_id, "error": str(exc)},
                )

        # 4c. GOVERNANCE (Step 6): policy and budget check when org_id present
        if organization_id and self._governance_engine is not None:
            try:
                estimated_cost = self._estimate_cost_for_model(
                    decision.model_name, prompt_to_use
                )
                allowed, reason = self._governance_engine.enforce_policy(
                    organization_id, decision.model_name, estimated_cost
                )
                if not allowed:
                    msg = reason or "Policy denied"
                    if "budget" in msg.lower() or "limit" in msg.lower():
                        raise BudgetExceededError(msg)
                    raise PermissionDeniedError(msg)
            except (BudgetExceededError, PermissionDeniedError):
                raise
            except Exception as exc:
                logger.warning(
                    "Governance check skipped",
                    extra={"request_id": request_id, "error": str(exc)},
                )

        # 5. EXECUTE INFERENCE (use enriched/optimized prompt)
        start = time.time()
        try:
            response_text, actual_input, actual_output, provider_latency = (
                self._execute_inference(decision.model_name, prompt_to_use)
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
                self._execute_inference(fallback_model.name, prompt_to_use)
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

        # 4d. GOVERNANCE: record spend for budget tracking
        if organization_id and self._governance_engine is not None:
            try:
                self._governance_engine.record_spend(organization_id, cost)
            except Exception as exc:
                logger.debug(
                    "Governance record_spend skipped",
                    extra={"request_id": request_id, "error": str(exc)},
                )

        # 5. STORE IN ALL CACHE TIERS (org-scoped for Tier 1 when organization_id present)
        # Tier 1: Exact match
        self._cache.set(
            query=prompt,
            response=response_text,
            model=decision.model_name,
            cost=cost,
            org_id=organization_id,
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
            organization_id=organization_id,
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
            cache_tier=0,
            routing_reason=decision.reason,
            request_id=request_id,
        )

    def get_metrics(self, org_id: Optional[str] = None) -> Dict[str, Any]:
        """Return current metrics summary including cache and uptime.

        Args:
            org_id: If set, only include events for this organization.

        Returns:
            Dict with analytics from the tracker plus cache stats and
            per-tier hit counts (tier1_hits, tier2_hits, tier3_hits).
        """
        summary: Dict[str, Any] = dict(self._tracker.get_metrics(org_id=org_id))
        cache_stats = self._cache.stats()
        summary["cache_size"] = cache_stats.entry_count
        # When org_id is set, keep org-scoped cache_hit_rate from tracker; otherwise use global cache stats
        if org_id is None:
            summary["cache_hit_rate"] = round(cache_stats.hit_rate, 4)
            summary["cache_cost_saved"] = cache_stats.total_cost_saved
        else:
            summary["cache_cost_saved"] = 0.0  # tracker does not provide per-org savings
        summary["uptime_seconds"] = round(time.time() - self._start_time, 1)
        summary["tier1_hits"] = cache_stats.hits
        summary["tier1_misses"] = cache_stats.misses
        if self._semantic_cache is not None:
            t2 = self._semantic_cache.stats()
            summary["tier2_hits"] = t2.get("hits", 0)
            summary["tier2_misses"] = t2.get("misses", 0)
        else:
            summary["tier2_hits"] = 0
            summary["tier2_misses"] = 0
        if self._intermediate_cache is not None:
            t3 = self._intermediate_cache.stats()
            summary["tier3_hits"] = t3.get("hits", 0)
            summary["tier3_misses"] = t3.get("misses", 0)
        else:
            summary["tier3_hits"] = 0
            summary["tier3_misses"] = 0
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

    def _check_cache(
        self, prompt: str, org_id: Optional[str] = None
    ) -> Optional[CacheEntry]:
        """Delegate cache lookup to the cache component."""
        return self._cache.get(prompt, org_id=org_id)

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

    def _estimate_cost_for_model(self, model_name: str, prompt: str) -> float:
        """Estimate cost for a given model and prompt (for governance checks)."""
        try:
            profile = self._registry.get(model_name)
        except Exception:
            return 0.0
        input_tokens = estimate_tokens(prompt)
        output_tokens = max(20, int(input_tokens * 0.6))
        return calculate_cost(profile, input_tokens, output_tokens)

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
        """Call the OpenAI API. Reuses a single client per process for connection pooling."""
        from openai import OpenAI

        with self._provider_lock:
            if self._openai_client is None:
                self._openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            client = self._openai_client
        start = time.time()
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
        """Call the Anthropic API. Reuses a single client per process for connection pooling."""
        import anthropic

        with self._provider_lock:
            if self._anthropic_client is None:
                self._anthropic_client = anthropic.Anthropic(
                    api_key=os.getenv("ANTHROPIC_API_KEY")
                )
            client = self._anthropic_client
        start = time.time()
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
        organization_id: Optional[str] = None,
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
            organization_id=organization_id,
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

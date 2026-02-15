"""
FastAPI application factory for Asahi inference optimizer.

Creates and configures the FastAPI app with all routes, middleware,
and shared state.  Includes analytics (Phase 6) and governance (Phase 7).
"""

import asyncio
import json
import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.api.middleware import RateLimiter
from src.config import get_settings
from src.api.schemas import (
    AnalyticsResponse,
    CostBreakdownRequest,
    ErrorResponse,
    ForecastRequest,
    HealthResponse,
    InferRequest,
    InferResponse,
    OpenAIChatRequest,
    OpenAIChatResponse,
    OpenAIChatChoice,
    OpenAIChatMessage,
    OpenAIUsage,
    TrendRequest,
)
from src.cache.exact import Cache
from src.cache.intermediate import IntermediateCache
from src.cache.redis_backend import RedisCache
from src.cache.semantic import SemanticCache
from src.cache.workflow import WorkflowDecomposer
from src.core.optimizer import InferenceOptimizer, InferenceResult
from src.embeddings.engine import EmbeddingEngine, EmbeddingConfig
from src.embeddings.mismatch import MismatchCostCalculator
from src.embeddings.similarity import SimilarityCalculator
from src.embeddings.threshold import AdaptiveThresholdTuner
from src.embeddings.vector_store import InMemoryVectorDB, PineconeVectorDB
from src.exceptions import (
    AsahiException,
    BatchingError,
    BudgetExceededError,
    ComplianceViolationError,
    ConfigurationError,
    EmbeddingError,
    FeatureConfigError,
    FeatureStoreError,
    ModelNotFoundError,
    NoModelsAvailableError,
    ObservabilityError,
    PermissionDeniedError,
    ProviderError,
    VectorDBError,
)
from src.routing.constraints import ConstraintInterpreter
from src.routing.router import AdvancedRouter, Router
from src.routing.task_detector import TaskTypeDetector
from src.governance.audit import AuditEntry, AuditLogger
from src.governance.auth import AuthMiddleware, AuthConfig
from src.governance.compliance import ComplianceManager
from src.governance.encryption import EncryptionManager
from src.governance.rbac import GovernanceEngine, OrganizationPolicy
from src.governance.tenancy import MultiTenancyManager
from src.governance.email import send_welcome_email
from src.observability.analytics import AnalyticsEngine
from src.observability.anomaly import AnomalyDetector
from src.observability.forecasting import ForecastingModel
from src.observability.metrics import MetricsCollector
from src.observability.recommendations import RecommendationEngine

logger = logging.getLogger(__name__)


def create_app(use_mock: bool = False) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        use_mock: If True, use mock inference (no real API calls).

    Returns:
        Configured FastAPI instance.
    """
    settings = get_settings()

    app = FastAPI(
        title="Asahi",
        description="LLM Inference Cost Optimization API",
        version=settings.api.version,
    )

     # -- Phase 2 components initialization (optional, graceful degradation) --
    semantic_cache: Optional[SemanticCache] = None
    intermediate_cache: Optional[IntermediateCache] = None
    workflow_decomposer: Optional[WorkflowDecomposer] = None
    advanced_router: Optional[AdvancedRouter] = None
    task_detector: Optional[TaskTypeDetector] = None
    constraint_interpreter: Optional[ConstraintInterpreter] = None

    try:
        # Initialize embedding engine for Tier 2
        embedding_config = EmbeddingConfig()
        embedding_engine = EmbeddingEngine(embedding_config)

        # Initialize vector DB: Pinecone when PINECONE_API_KEY set (Step 7), else in-memory
        vector_db: Any = InMemoryVectorDB()
        if os.environ.get("PINECONE_API_KEY"):
            try:
                vector_db = PineconeVectorDB(
                    index_name=os.environ.get("PINECONE_INDEX", "asahi-vectors"),
                    dimension=embedding_config.dimension,
                )
                logger.info("Tier 2 using Pinecone vector DB", extra={})
            except Exception as exc:
                logger.warning(
                    "Pinecone init failed, using in-memory vector DB",
                    extra={"error": str(exc)},
                )
                vector_db = InMemoryVectorDB()

        # Initialize Tier 2 semantic cache dependencies
        similarity_calc = SimilarityCalculator()
        mismatch_calc = MismatchCostCalculator()
        threshold_tuner = AdaptiveThresholdTuner()

        # Create semantic cache
        semantic_cache = SemanticCache(
            embedding_engine=embedding_engine,
            vector_db=vector_db,
            similarity_calc=similarity_calc,
            mismatch_calc=mismatch_calc,
            threshold_tuner=threshold_tuner,
            ttl_seconds=settings.cache.ttl_seconds,
        )

        # Initialize Tier 3 components
        intermediate_cache = IntermediateCache(
            ttl_seconds=settings.cache.ttl_seconds
        )
        workflow_decomposer = WorkflowDecomposer()

        # Initialize advanced routing components
        task_detector = TaskTypeDetector()
        constraint_interpreter = ConstraintInterpreter()
        
        # Create base router and registry for advanced router
        from src.models.registry import ModelRegistry
        registry = ModelRegistry()
        base_router = Router(registry)
        
        advanced_router = AdvancedRouter(
            registry=registry,
            base_router=base_router,
            task_detector=task_detector,
            constraint_interpreter=constraint_interpreter,
        )

        logger.info("Phase 2 components initialized successfully")
    except Exception as exc:
        logger.warning(
            "Phase 2 components initialization failed, continuing with Phase 1 only",
            extra={"error": str(exc)},
            exc_info=True,
        )

    # -- Tier 1 cache: Redis if REDIS_URL set, else in-memory --
    tier1_cache: Optional[Any] = None
    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        try:
            tier1_cache = RedisCache(
                redis_url=redis_url,
                ttl_seconds=settings.cache.ttl_seconds,
            )
            logger.info("Tier 1 cache using Redis", extra={"redis_url": "***"})
        except Exception as exc:
            logger.warning(
                "Redis cache init failed, using in-memory Tier 1",
                extra={"error": str(exc)},
            )
    if tier1_cache is None:
        tier1_cache = Cache(ttl_seconds=settings.cache.ttl_seconds)

    # -- Step 3 (TokenOptimizer) & Step 4 (FeatureEnricher) - optional --
    token_optimizer: Optional[Any] = None
    feature_enricher: Optional[Any] = None
    try:
        from pathlib import Path
        from src.optimization.analyzer import AnalyzerConfig, ContextAnalyzer
        from src.optimization.compressor import CompressorConfig, PromptCompressor
        from src.optimization.optimizer import OptimizerConfig, TokenOptimizer as TO
        analyzer = ContextAnalyzer(config=AnalyzerConfig(scoring_method="keyword"))
        compressor = PromptCompressor(config=CompressorConfig())
        token_optimizer = TO(
            analyzer=analyzer,
            compressor=compressor,
            few_shot_selector=None,
            config=OptimizerConfig(),
        )
        logger.info("TokenOptimizer (Step 3) initialised", extra={})
    except Exception as exc:
        logger.warning(
            "TokenOptimizer init failed, continuing without token optimization",
            extra={"error": str(exc)},
        )
    try:
        from src.features.client import LocalFeatureStore
        from src.features.enricher import EnricherConfig, FeatureEnricher as FE
        fs_path = Path(settings.feature_store.local_data_path)
        feature_store_client = LocalFeatureStore(data_path=fs_path)
        feature_enricher = FE(
            client=feature_store_client,
            config=EnricherConfig(),
        )
        logger.info("FeatureEnricher (Step 4) initialised", extra={})
    except Exception as exc:
        logger.warning(
            "FeatureEnricher init failed, continuing without enrichment",
            extra={"error": str(exc)},
        )

    # -- Step 5 (BatchEngine + queue/scheduler for full batching) --
    batch_engine: Optional[Any] = None
    try:
        from src.batching.engine import BatchEngine, BatchConfig
        from src.models.registry import ModelRegistry
        batch_engine = BatchEngine(
            config=BatchConfig(),
            model_registry=ModelRegistry(),
        )
        logger.info("BatchEngine (Step 5) initialised", extra={})
    except Exception as exc:
        logger.warning(
            "BatchEngine init failed, continuing without batch eligibility",
            extra={"error": str(exc)},
        )

    # -- Shared state --
    app.state.optimizer = InferenceOptimizer(
        cache=tier1_cache,
        use_mock=use_mock,
        semantic_cache=semantic_cache,
        intermediate_cache=intermediate_cache,
        workflow_decomposer=workflow_decomposer,
        advanced_router=advanced_router,
        task_detector=task_detector,
        constraint_interpreter=constraint_interpreter,
        token_optimizer=token_optimizer,
        feature_enricher=feature_enricher,
        batch_engine=batch_engine,
    )

    # -- Step 5 full batching: queue + scheduler (executor runs optimizer.infer per request) --
    if batch_engine is not None:
        try:
            from src.batching.queue import RequestQueue
            from src.batching.scheduler import BatchScheduler
            from src.batching.engine import BatchConfig

            request_queue = RequestQueue()
            optimizer_ref = app.state.optimizer

            def batch_executor(batch: list) -> list:
                return [
                    optimizer_ref.infer(**req.infer_kwargs)
                    for req in batch
                ]

            batch_scheduler = BatchScheduler(
                queue=request_queue,
                executor=batch_executor,
                config=BatchConfig(),
                poll_interval_ms=50,
            )
            batch_scheduler.start()
            app.state.optimizer._request_queue = request_queue
            app.state.optimizer._batch_scheduler = batch_scheduler
            app.state.batch_scheduler = batch_scheduler
            logger.info("Batch queue and scheduler started", extra={})
        except Exception as exc:
            logger.warning(
                "Batch queue/scheduler init failed, batching disabled",
                extra={"error": str(exc)},
            )

    app.state.start_time = time.time()
    app.state.version = settings.api.version
    app.state.rate_limiter = RateLimiter(
        max_requests=settings.api.rate_limit_per_minute, window_seconds=60
    )

    # -- Observability (Phase 6) --
    app.state.metrics_collector = MetricsCollector()
    app.state.analytics_engine = AnalyticsEngine(app.state.metrics_collector)
    app.state.forecasting_model = ForecastingModel(app.state.analytics_engine)
    app.state.anomaly_detector = AnomalyDetector(app.state.analytics_engine)
    app.state.recommendation_engine = RecommendationEngine(
        app.state.analytics_engine
    )

    # -- Governance (Phase 7) --
    try:
        app.state.encryption_manager = EncryptionManager()
    except Exception:
        logger.warning(
            "EncryptionManager unavailable (ASAHI_ENCRYPTION_KEY not set)",
            extra={},
        )
        app.state.encryption_manager = None

    app.state.audit_logger = AuditLogger()
    app.state.governance_engine = GovernanceEngine()
    app.state.compliance_manager = ComplianceManager(
        audit_logger=app.state.audit_logger
    )
    app.state.tenancy_manager = MultiTenancyManager()
    # Step 6: wire governance into optimizer for policy/budget checks
    app.state.optimizer._governance_engine = app.state.governance_engine

    # -- Auth: DB-backed API keys when DATABASE_URL is set (e.g. Railway) --
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        # Railway and some providers use postgres://; SQLAlchemy/psycopg2 expect postgresql://
        if database_url.startswith("postgres://"):
            database_url = "postgresql://" + database_url[11:]
        try:
            from src.db.engine import get_engine, get_session_factory, init_db, init_async_engine
            from src.db.repositories import ApiKeyRepository, OrgRepository
            from src.db.key_store import DbKeyStore

            db_engine = get_engine(database_url)
            init_db(db_engine)
            init_async_engine(database_url)
            db_session_factory = get_session_factory(db_engine)
            api_key_repo = ApiKeyRepository(db_session_factory)
            app.state.org_repository = OrgRepository(db_session_factory)
            db_key_store = DbKeyStore(api_key_repo)
            app.state.auth_middleware = AuthMiddleware(key_store=db_key_store)
            logger.info("Auth using PostgreSQL API key store", extra={})
        except Exception as exc:
            logger.warning(
                "Database auth init failed, using in-memory auth: %s",
                str(exc),
                extra={"error": str(exc)},
            )
            app.state.auth_middleware = AuthMiddleware()
    else:
        app.state.auth_middleware = AuthMiddleware()

    # -- CORS --
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -- Request-ID middleware --
    @app.middleware("http")
    async def add_request_id(request: Request, call_next: Any) -> Response:
        """Attach a unique request ID to every request."""
        request_id = request.headers.get(
            "X-Request-Id", uuid.uuid4().hex[:12]
        )
        request.state.request_id = request_id
        response: Response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response

    # -- Rate limiting middleware --
    @app.middleware("http")
    async def rate_limit(request: Request, call_next: Any) -> Response:
        """Enforce per-IP rate limiting."""
        client_ip = request.client.host if request.client else "unknown"
        limiter: RateLimiter = request.app.state.rate_limiter

        if not limiter.is_allowed(client_ip):
            return Response(
                content='{"error":"rate_limit_exceeded","message":"Too many requests"}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": "60"},
            )
        return await call_next(request)

    # -- Auth middleware (Phase 7) --
    @app.middleware("http")
    async def auth_middleware(request: Request, call_next: Any) -> Response:
        """Authenticate requests via API key when enabled."""
        auth: AuthMiddleware = request.app.state.auth_middleware
        if request.url.path in ("/health", "/docs", "/openapi.json", "/redoc"):
            return await call_next(request)
        result = auth.authenticate(dict(request.headers))
        request.state.auth = result
        if not result.authenticated and auth._config.api_key_required:
            try:
                al: AuditLogger = request.app.state.audit_logger
                al.log(
                    AuditEntry(
                        org_id="unknown",
                        user_id="anonymous",
                        action="auth_failure",
                        resource=request.url.path or "/",
                        result="denied",
                        details={"reason": "invalid_or_missing_key"},
                    )
                )
            except Exception:
                pass
            return Response(
                content='{"error":"unauthorized","message":"Valid API key required"}',
                status_code=401,
                media_type="application/json",
            )
        return await call_next(request)

    # -- Global exception handlers --
    @app.exception_handler(AsahiException)
    async def asahi_exception_handler(
        request: Request, exc: AsahiException
    ) -> Response:
        """Handle all AsahiException subclasses with consistent JSON."""
        request_id = getattr(request.state, "request_id", "unknown")

        # Map exception types to HTTP status codes
        status_map = {
            NoModelsAvailableError: 503,
            ProviderError: 503,
            ModelNotFoundError: 400,
            ConfigurationError: 400,
            FeatureConfigError: 400,
            EmbeddingError: 502,
            VectorDBError: 502,
            FeatureStoreError: 502,
            ObservabilityError: 502,
            BatchingError: 502,
            BudgetExceededError: 429,
            PermissionDeniedError: 403,
            ComplianceViolationError: 403,
        }
        status_code = status_map.get(type(exc), 500)

        # Convert exception class name to error type (e.g., "NoModelsAvailableError" -> "nomodelsavailable")
        error_type = exc.__class__.__name__.replace("Error", "").lower()

        return Response(
            content=json.dumps(
                {
                    "error": error_type,
                    "message": str(exc),
                    "request_id": request_id,
                }
            ),
            status_code=status_code,
            media_type="application/json",
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(
        request: Request, exc: Exception
    ) -> Response:
        """Catch-all handler for unhandled exceptions."""
        request_id = getattr(request.state, "request_id", "unknown")
        logger.error(
            "Unhandled exception",
            extra={"request_id": request_id, "error": str(exc)},
            exc_info=True,
        )
        return Response(
            content=json.dumps(
                {
                    "error": "internal_server_error",
                    "message": "An unexpected error occurred",
                    "request_id": request_id,
                }
            ),
            status_code=500,
            media_type="application/json",
        )

    # -- Routes --
    from src.api.auth import auth_router
    app.include_router(auth_router)

    def _require_scope(request: Request, allowed: List[str]) -> None:
        """Raise 403 if the key has scopes and none of allowed are present (Step 6 RBAC)."""
        if not hasattr(request.state, "auth"):
            return
        auth = request.state.auth
        if not auth.authenticated:
            return
        scopes = getattr(auth, "scopes", []) or []
        if not scopes:
            return  # no scopes = legacy key, allow
        if "*" in scopes:
            return  # wildcard = full access
        if any(s in scopes for s in allowed):
            return
        raise HTTPException(
            status_code=403,
            detail=f"One of scopes {allowed} required for this endpoint",
        )

    def _require_governance_admin(request: Request) -> None:
        """Raise 403 if the request is authenticated but key does not have admin scope (Step 6 RBAC)."""
        _require_scope(request, ["admin", "all"])

    async def _require_analytics_scope(request: Request) -> None:
        """Dependency: require analytics, admin, or all scope for analytics endpoints."""
        _require_scope(request, ["analytics", "admin", "all"])

    @app.post(
        "/infer",
        response_model=InferResponse,
        responses={
            400: {"model": ErrorResponse},
            429: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
        summary="Run inference with smart routing and caching",
    )
    async def infer(body: InferRequest, request: Request) -> InferResponse:
        """Run an inference request through Asahi's optimizer."""
        _require_scope(request, ["infer", "all"])
        optimizer: InferenceOptimizer = request.app.state.optimizer
        request_id: str = getattr(
            request.state, "request_id", uuid.uuid4().hex[:12]
        )

        org_id = body.organization_id or (
            getattr(request.state.auth, "org_id", None) if hasattr(request.state, "auth") else None
        )
        logger.info(
            "Inference request",
            extra={"request_id": request_id, "org_id": org_id or "default"},
        )
        result: InferenceResult = await asyncio.to_thread(
            optimizer.infer,
            prompt=body.prompt,
            task_id=body.task_id,
            latency_budget_ms=body.latency_budget_ms,
            quality_threshold=body.quality_threshold,
            cost_budget=body.cost_budget,
            user_id=body.user_id,
            organization_id=org_id,
            routing_mode=body.routing_mode,
            quality_preference=body.quality_preference,
            latency_preference=body.latency_preference,
            model_override=body.model_override,
            document_id=body.document_id,
        )

        try:
            al: AuditLogger = request.app.state.audit_logger
            al.log(
                AuditEntry(
                    org_id=org_id or "default",
                    user_id=(
                        body.user_id
                        or (getattr(request.state.auth, "user_id", None) if hasattr(request.state, "auth") else None)
                        or "anonymous"
                    ),
                    action="inference",
                    resource="infer",
                    details={
                        "request_id": request_id,
                        "model_used": result.model_used,
                        "cache_hit": result.cache_hit,
                        "cache_tier": result.cache_tier,
                        "cost": result.cost,
                    },
                    result="success",
                )
            )
        except Exception:
            pass

        logger.info(
            "Inference completed",
            extra={
                "request_id": request_id,
                "org_id": org_id or "default",
                "cache_hit": result.cache_hit,
                "cache_tier": result.cache_tier,
                "model_used": result.model_used,
                "cost": result.cost,
            },
        )
        return InferResponse(
            request_id=request_id,
            response=result.response,
            model_used=result.model_used,
            tokens_input=result.tokens_input,
            tokens_output=result.tokens_output,
            cost=result.cost,
            latency_ms=result.latency_ms,
            cache_hit=result.cache_hit,
            cache_tier=result.cache_tier,
            routing_reason=result.routing_reason,
            cost_original=result.cost_original,
            cost_savings_percent=result.cost_savings_percent,
            optimization_techniques=result.optimization_techniques,
        )

    def _messages_to_prompt(messages: List[Dict[str, Any]]) -> str:
        """Convert OpenAI messages to a single prompt string.

        Concatenates system, user, and assistant messages for Asahi inference.
        """
        parts: List[str] = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content") or ""
            if isinstance(content, list):
                content = " ".join(
                    (
                        item.get("text", "")
                        for item in content
                        if isinstance(item, dict)
                    )
                )
            if content:
                parts.append(f"{role}: {content}")
        return "\n\n".join(parts) if parts else ""

    @app.post(
        "/v1/chat/completions",
        response_model=OpenAIChatResponse,
        summary="OpenAI-compatible chat completions",
    )
    async def openai_chat_completions(
        body: OpenAIChatRequest,
        request: Request,
    ) -> OpenAIChatResponse:
        """Run inference via OpenAI-compatible API; Asahi applies routing and caching."""
        optimizer: InferenceOptimizer = request.app.state.optimizer
        request_id: str = getattr(
            request.state, "request_id", uuid.uuid4().hex[:12]
        )
        prompt = _messages_to_prompt([m.model_dump() for m in body.messages])
        if not prompt or not prompt.strip():
            raise HTTPException(
                status_code=400,
                detail="messages must contain at least one non-empty message",
            )
        result: InferenceResult = await asyncio.to_thread(
            optimizer.infer,
            prompt=prompt,
            routing_mode="explicit" if body.model else "autopilot",
            model_override=body.model,
        )
        return OpenAIChatResponse(
            id=request_id,
            choices=[
                OpenAIChatChoice(
                    index=0,
                    message=OpenAIChatMessage(
                        role="assistant",
                        content=result.response,
                    ),
                    finish_reason="stop",
                )
            ],
            usage=OpenAIUsage(
                prompt_tokens=result.tokens_input,
                completion_tokens=result.tokens_output,
                total_tokens=result.tokens_input + result.tokens_output,
            ),
            model=result.model_used or (body.model or "asahi"),
        )

    @app.get(
        "/metrics",
        summary="View cost, latency, and quality analytics",
    )
    async def metrics(request: Request) -> Dict[str, Any]:
        """Return aggregated analytics for all inference events."""
        optimizer: InferenceOptimizer = request.app.state.optimizer
        return optimizer.get_metrics()

    @app.get(
        "/models",
        summary="List available LLM models with pricing",
    )
    async def models(request: Request) -> Dict[str, Any]:
        """Return all registered model profiles."""
        optimizer: InferenceOptimizer = request.app.state.optimizer
        return optimizer.registry.to_dict()

    @app.get(
        "/health",
        response_model=HealthResponse,
        summary="Service health check",
    )
    async def health(request: Request) -> HealthResponse:
        """Return service health status and component statuses."""
        optimizer: InferenceOptimizer = request.app.state.optimizer
        return HealthResponse(
            status="healthy",
            version=request.app.state.version,
            uptime_seconds=round(
                time.time() - request.app.state.start_time, 1
            ),
            components={
                "cache": "healthy",
                "router": "healthy",
                "tracker": "healthy",
                "registry": (
                    "healthy"
                    if len(optimizer.registry) > 0
                    else "degraded"
                ),
                "observability": "healthy",
                "governance": "healthy",
            },
        )

    # -- Analytics endpoints (Phase 6) --

    @app.get(
        "/analytics/cost-breakdown",
        response_model=AnalyticsResponse,
        summary="Cost breakdown by model/task/period",
    )
    async def cost_breakdown(
        request: Request,
        period: str = "day",
        group_by: str = "model",
        _: None = Depends(_require_analytics_scope),
    ) -> AnalyticsResponse:
        """Return cost breakdown grouped by model, task type, or tier."""
        engine: AnalyticsEngine = request.app.state.analytics_engine
        data = engine.cost_breakdown(period=period, group_by=group_by)  # type: ignore[arg-type]
        return AnalyticsResponse(data=data)

    @app.get(
        "/analytics/trends",
        response_model=AnalyticsResponse,
        summary="Time-series trend data",
    )
    async def trends(
        request: Request,
        metric: str = "cost",
        period: str = "day",
        intervals: int = 30,
        _: None = Depends(_require_analytics_scope),
    ) -> AnalyticsResponse:
        """Return time-series trend data for the given metric."""
        engine: AnalyticsEngine = request.app.state.analytics_engine
        data = engine.trend(metric=metric, period=period, intervals=intervals)
        return AnalyticsResponse(data=data)

    @app.get(
        "/analytics/forecast",
        response_model=AnalyticsResponse,
        summary="Cost forecast",
    )
    async def forecast(
        request: Request,
        horizon_days: int = 30,
        monthly_budget: float = 0.0,
        _: None = Depends(_require_analytics_scope),
    ) -> AnalyticsResponse:
        """Return cost forecast and optional budget risk assessment."""
        model: ForecastingModel = request.app.state.forecasting_model
        cost_forecast = model.predict_cost(horizon_days=horizon_days)
        budget_risk = (
            model.detect_budget_risk(monthly_budget)
            if monthly_budget > 0
            else None
        )
        return AnalyticsResponse(
            data={
                "forecast": cost_forecast.model_dump(),
                "budget_risk": budget_risk,
            }
        )

    @app.get(
        "/analytics/recent-inferences",
        response_model=AnalyticsResponse,
        summary="Last N inference events for dashboard table",
    )
    async def recent_inferences(
        request: Request,
        limit: int = 50,
        _: None = Depends(_require_analytics_scope),
    ) -> AnalyticsResponse:
        """Return the most recent inference events (request_id, model_used, cost, cache_hit, etc.)."""
        optimizer: InferenceOptimizer = request.app.state.optimizer
        events = optimizer.tracker.get_events(limit=min(limit, 500))
        data = [
            {
                "request_id": e.request_id,
                "timestamp": e.timestamp.isoformat(),
                "model_used": e.model_selected,
                "cost": e.cost,
                "cache_hit": e.cache_hit,
                "latency_ms": e.latency_ms,
                "routing_reason": e.routing_reason,
                "input_tokens": e.input_tokens,
                "output_tokens": e.output_tokens,
            }
            for e in events
        ]
        return AnalyticsResponse(data={"inferences": data, "count": len(data)})

    @app.get(
        "/analytics/cost-summary",
        response_model=AnalyticsResponse,
        summary="Cost summary for dashboard (period is informational)",
    )
    async def cost_summary(
        request: Request,
        period: str = "24h",
        _: None = Depends(_require_analytics_scope),
    ) -> AnalyticsResponse:
        """Return cost and savings summary for the dashboard.
        Period is informational; metrics are since process start unless
        analytics backend supports time windows."""
        optimizer: InferenceOptimizer = request.app.state.optimizer
        metrics = optimizer.get_metrics()
        data = {
            "period": period,
            "total_cost": metrics.get("total_cost", 0.0),
            "total_requests": metrics.get("requests", 0),
            "cache_hit_rate": metrics.get("cache_hit_rate", 0.0),
            "cache_cost_saved": metrics.get("cache_cost_saved", 0.0),
            "estimated_savings_vs_gpt4": metrics.get("estimated_savings_vs_gpt4", 0.0),
            "absolute_savings": metrics.get("absolute_savings", 0.0),
            "uptime_seconds": metrics.get("uptime_seconds", 0.0),
        }
        return AnalyticsResponse(data=data)

    @app.get(
        "/analytics/anomalies",
        response_model=AnalyticsResponse,
        summary="Current anomalies",
    )
    async def anomalies(
        request: Request,
        _: None = Depends(_require_analytics_scope),
    ) -> AnalyticsResponse:
        """Return any currently detected anomalies."""
        detector: AnomalyDetector = request.app.state.anomaly_detector
        results = detector.check()
        return AnalyticsResponse(
            data=[a.model_dump() for a in results]
        )

    @app.get(
        "/analytics/recommendations",
        response_model=AnalyticsResponse,
        summary="Active recommendations",
    )
    async def recommendations(
        request: Request,
        _: None = Depends(_require_analytics_scope),
    ) -> AnalyticsResponse:
        """Return actionable optimization recommendations."""
        engine: RecommendationEngine = request.app.state.recommendation_engine
        results = engine.generate()
        return AnalyticsResponse(
            data=[r.model_dump() for r in results]
        )

    @app.get(
        "/analytics/cache-performance",
        response_model=AnalyticsResponse,
        summary="Cache performance per tier",
    )
    async def cache_performance(
        request: Request,
        _: None = Depends(_require_analytics_scope),
    ) -> AnalyticsResponse:
        """Return per-tier and overall cache performance."""
        engine: AnalyticsEngine = request.app.state.analytics_engine
        return AnalyticsResponse(data=engine.cache_performance())

    @app.get(
        "/analytics/latency-percentiles",
        response_model=AnalyticsResponse,
        summary="Latency percentiles",
    )
    async def latency_percentiles(
        request: Request,
        _: None = Depends(_require_analytics_scope),
    ) -> AnalyticsResponse:
        """Return latency percentiles (p50, p75, p90, p95, p99)."""
        engine: AnalyticsEngine = request.app.state.analytics_engine
        return AnalyticsResponse(data=engine.latency_percentiles())

    @app.get(
        "/analytics/prometheus",
        summary="Prometheus metrics endpoint",
    )
    async def prometheus_metrics(
        request: Request,
        _: None = Depends(_require_analytics_scope),
    ) -> Response:
        """Return metrics in Prometheus text exposition format."""
        collector: MetricsCollector = request.app.state.metrics_collector
        return Response(
            content=collector.get_prometheus_metrics(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    # -- Self-serve signup (Phase 3.2) --

    class SignupRequest(BaseModel):
        org_name: str = Field(..., min_length=1, max_length=255)
        user_id: str = Field(..., min_length=1, max_length=255)
        email: Optional[str] = Field(None, max_length=255)

    @app.post(
        "/signup",
        summary="Self-serve signup: create org and API key",
    )
    async def signup(body: SignupRequest, request: Request) -> Dict[str, Any]:
        """Create a new organisation and API key. Requires DATABASE_URL. Optionally sends welcome email if SENDGRID_API_KEY is set."""
        org_repo = getattr(request.app.state, "org_repository", None)
        if org_repo is None:
            raise HTTPException(
                status_code=503,
                detail="Signup is not available (DATABASE_URL not configured)",
            )
        org = org_repo.create_org(body.org_name, plan="startup")
        org_id = str(org.id)
        auth: AuthMiddleware = request.app.state.auth_middleware
        key = auth.generate_api_key(body.user_id, org_id, scopes=["*"])
        if body.email and "@" in body.email:
            send_welcome_email(body.email, body.org_name, key[:12])
        return {
            "org_id": org_id,
            "org_name": org.name,
            "api_key": key,
            "prefix": key[:12],
            "user_id": body.user_id,
            "message": "Store your API key securely; it is shown only once.",
        }

    # -- Governance endpoints (Phase 7) --

    class ApiKeyRequest(BaseModel):
        user_id: str
        org_id: str
        scopes: List[str] = Field(default_factory=list)

    class PolicyRequest(BaseModel):
        allowed_models: List[str] = Field(default_factory=list)
        blocked_models: List[str] = Field(default_factory=list)
        max_cost_per_day: Optional[float] = None
        max_cost_per_request: Optional[float] = None
        max_requests_per_day: Optional[int] = None

    @app.post(
        "/governance/api-keys",
        summary="Generate a new API key (stored in DB when DATABASE_URL is set)",
    )
    async def create_api_key(
        body: ApiKeyRequest, request: Request
    ) -> Dict[str, Any]:
        """Generate a new API key for a user. When DATABASE_URL is set, key is persisted to PostgreSQL."""
        admin_secret = os.environ.get("ASAHI_ADMIN_SECRET")
        if admin_secret:
            provided = request.headers.get("X-Admin-Secret", "")
            if provided != admin_secret:
                raise HTTPException(
                    status_code=403,
                    detail="X-Admin-Secret required to create API keys",
                )
        else:
            _require_governance_admin(request)
        auth: AuthMiddleware = request.app.state.auth_middleware
        key = auth.generate_api_key(body.user_id, body.org_id, body.scopes)
        try:
            request.app.state.audit_logger.log(
                AuditEntry(
                    org_id=body.org_id,
                    user_id=body.user_id,
                    action="api_key_created",
                    resource="api_keys",
                    details={"prefix": key[:12]},
                    result="success",
                )
            )
        except Exception:
            pass
        return {
            "api_key": key,
            "prefix": key[:12],
            "user_id": body.user_id,
            "org_id": body.org_id,
        }

    @app.get(
        "/governance/audit",
        summary="Query audit log",
    )
    async def query_audit(
        request: Request,
        org_id: str = "default",
        action: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Query audit log entries for an organisation."""
        _require_governance_admin(request)
        al: AuditLogger = request.app.state.audit_logger
        entries = al.query(
            org_id=org_id, action=action, user_id=user_id, limit=limit
        )
        return {
            "org_id": org_id,
            "count": len(entries),
            "entries": [e.model_dump(mode="json") for e in entries],
        }

    @app.get(
        "/governance/usage",
        summary="Get organisation usage and cost",
    )
    async def get_usage(
        request: Request,
        org_id: str = "default",
        period: str = "day",
    ) -> Dict[str, Any]:
        """Return request count and total cost for an organisation over a period (day=24h, month=720h). Admin only."""
        _require_governance_admin(request)
        period_hours = 720 if period == "month" else 24
        ge: GovernanceEngine = request.app.state.governance_engine
        request_count, total_cost_usd = ge.get_usage(org_id, period_hours)
        policy = ge.get_policy(org_id)
        out: Dict[str, Any] = {
            "org_id": org_id,
            "period": period,
            "period_hours": period_hours,
            "request_count": request_count,
            "total_cost_usd": total_cost_usd,
        }
        if policy:
            out["policy_limits"] = {
                "max_requests_per_day": policy.max_requests_per_day,
                "max_cost_per_day": policy.max_cost_per_day,
                "max_cost_per_request": policy.max_cost_per_request,
            }
        return out

    @app.get(
        "/governance/compliance/report",
        summary="Generate compliance report",
    )
    async def compliance_report(
        request: Request,
        org_id: str = "default",
        framework: str = "hipaa",
    ) -> Dict[str, Any]:
        """Generate a compliance status report."""
        _require_governance_admin(request)
        cm: ComplianceManager = request.app.state.compliance_manager
        return cm.generate_compliance_report(org_id, framework)

    @app.get(
        "/governance/policies/{org_id}",
        summary="Get organisation policy",
    )
    async def get_policy(org_id: str, request: Request) -> Dict[str, Any]:
        """Retrieve governance policy for an organisation."""
        _require_governance_admin(request)
        ge: GovernanceEngine = request.app.state.governance_engine
        policy = ge.get_policy(org_id)
        if not policy:
            raise HTTPException(status_code=404, detail="Policy not found")
        return policy.model_dump(mode="json")

    @app.post(
        "/governance/policies/{org_id}",
        summary="Create or update organisation policy",
    )
    async def set_policy(
        org_id: str, body: PolicyRequest, request: Request
    ) -> Dict[str, Any]:
        """Create or update a governance policy for an organisation."""
        _require_governance_admin(request)
        ge: GovernanceEngine = request.app.state.governance_engine
        policy = OrganizationPolicy(
            org_id=org_id,
            allowed_models=body.allowed_models,
            blocked_models=body.blocked_models,
            max_cost_per_day=body.max_cost_per_day,
            max_cost_per_request=body.max_cost_per_request,
            max_requests_per_day=body.max_requests_per_day,
        )
        ge.create_policy(policy)
        try:
            request.app.state.audit_logger.log(
                AuditEntry(
                    org_id=org_id,
                    user_id=getattr(request.state.auth, "user_id", None) or "system",
                    action="policy_update",
                    resource="policies",
                    details={
                        "allowed_models": body.allowed_models,
                        "blocked_models": body.blocked_models,
                        "max_cost_per_day": body.max_cost_per_day,
                        "max_cost_per_request": body.max_cost_per_request,
                        "max_requests_per_day": body.max_requests_per_day,
                    },
                    result="success",
                )
            )
        except Exception:
            pass
        return {"status": "created", "org_id": org_id}

    return app

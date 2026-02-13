"""
FastAPI application factory for Asahi inference optimizer.

Creates and configures the FastAPI app with all routes, middleware,
and shared state.  Includes analytics (Phase 6) and governance (Phase 7).
"""

import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, Response
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
    TrendRequest,
)
from src.cache.intermediate import IntermediateCache
from src.cache.semantic import SemanticCache
from src.cache.workflow import WorkflowDecomposer
from src.core.optimizer import InferenceOptimizer, InferenceResult
from src.embeddings.engine import EmbeddingEngine, EmbeddingConfig
from src.embeddings.mismatch import MismatchCostCalculator
from src.embeddings.similarity import SimilarityCalculator
from src.embeddings.threshold import AdaptiveThresholdTuner
from src.embeddings.vector_store import InMemoryVectorDB
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
from src.governance.audit import AuditLogger
from src.governance.auth import AuthMiddleware, AuthConfig
from src.governance.compliance import ComplianceManager
from src.governance.encryption import EncryptionManager
from src.governance.rbac import GovernanceEngine, OrganizationPolicy
from src.governance.tenancy import MultiTenancyManager
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

        # Initialize vector DB (in-memory for now, can be swapped for Pinecone)
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

    # -- Shared state --
    app.state.optimizer = InferenceOptimizer(
        use_mock=use_mock,
        semantic_cache=semantic_cache,
        intermediate_cache=intermediate_cache,
        workflow_decomposer=workflow_decomposer,
        advanced_router=advanced_router,
        task_detector=task_detector,
        constraint_interpreter=constraint_interpreter,
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
        optimizer: InferenceOptimizer = request.app.state.optimizer
        request_id: str = getattr(
            request.state, "request_id", uuid.uuid4().hex[:12]
        )

        result: InferenceResult = optimizer.infer(
            prompt=body.prompt,
            task_id=body.task_id,
            latency_budget_ms=body.latency_budget_ms,
            quality_threshold=body.quality_threshold,
            cost_budget=body.cost_budget,
            user_id=body.user_id,
            routing_mode=body.routing_mode,
            quality_preference=body.quality_preference,
            latency_preference=body.latency_preference,
            model_override=body.model_override,
            document_id=body.document_id,
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
            routing_reason=result.routing_reason,
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
        "/analytics/anomalies",
        response_model=AnalyticsResponse,
        summary="Current anomalies",
    )
    async def anomalies(request: Request) -> AnalyticsResponse:
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
    async def recommendations(request: Request) -> AnalyticsResponse:
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
    async def cache_performance(request: Request) -> AnalyticsResponse:
        """Return per-tier and overall cache performance."""
        engine: AnalyticsEngine = request.app.state.analytics_engine
        return AnalyticsResponse(data=engine.cache_performance())

    @app.get(
        "/analytics/latency-percentiles",
        response_model=AnalyticsResponse,
        summary="Latency percentiles",
    )
    async def latency_percentiles(request: Request) -> AnalyticsResponse:
        """Return latency percentiles (p50, p75, p90, p95, p99)."""
        engine: AnalyticsEngine = request.app.state.analytics_engine
        return AnalyticsResponse(data=engine.latency_percentiles())

    @app.get(
        "/analytics/prometheus",
        summary="Prometheus metrics endpoint",
    )
    async def prometheus_metrics(request: Request) -> Response:
        """Return metrics in Prometheus text exposition format."""
        collector: MetricsCollector = request.app.state.metrics_collector
        return Response(
            content=collector.get_prometheus_metrics(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

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
        summary="Generate a new API key",
    )
    async def create_api_key(
        body: ApiKeyRequest, request: Request
    ) -> Dict[str, Any]:
        """Generate a new API key for a user."""
        auth: AuthMiddleware = request.app.state.auth_middleware
        key = auth.generate_api_key(body.user_id, body.org_id, body.scopes)
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
        "/governance/compliance/report",
        summary="Generate compliance report",
    )
    async def compliance_report(
        request: Request,
        org_id: str = "default",
        framework: str = "hipaa",
    ) -> Dict[str, Any]:
        """Generate a compliance status report."""
        cm: ComplianceManager = request.app.state.compliance_manager
        return cm.generate_compliance_report(org_id, framework)

    @app.get(
        "/governance/policies/{org_id}",
        summary="Get organisation policy",
    )
    async def get_policy(org_id: str, request: Request) -> Dict[str, Any]:
        """Retrieve governance policy for an organisation."""
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
        return {"status": "created", "org_id": org_id}

    return app

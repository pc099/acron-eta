"""
FastAPI application factory for Asahi inference optimizer.

Creates and configures the FastAPI app with all routes, middleware,
and shared state.  Includes analytics (Phase 6) and governance (Phase 7).
"""

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.api.middleware import RateLimiter
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
from src.core.optimizer import InferenceOptimizer, InferenceResult
from src.exceptions import (
    BudgetExceededError,
    ComplianceViolationError,
    NoModelsAvailableError,
    ObservabilityError,
    PermissionDeniedError,
    ProviderError,
)
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
    app = FastAPI(
        title="Asahi",
        description="LLM Inference Cost Optimization API",
        version="1.0.0",
    )

    # -- Shared state --
    app.state.optimizer = InferenceOptimizer(use_mock=use_mock)
    app.state.start_time = time.time()
    app.state.version = "1.0.0"
    app.state.rate_limiter = RateLimiter(max_requests=100, window_seconds=60)

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
    app.state.auth_middleware = AuthMiddleware(
        config=AuthConfig(api_key_required=False)
    )

    # -- CORS --
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
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

    # -- Exception handlers (Phase 7) --
    @app.exception_handler(BudgetExceededError)
    async def budget_exceeded_handler(
        request: Request, exc: BudgetExceededError
    ) -> Response:
        return Response(
            content=f'{{"error":"budget_exceeded","message":"{exc}"}}',
            status_code=429,
            media_type="application/json",
        )

    @app.exception_handler(PermissionDeniedError)
    async def permission_denied_handler(
        request: Request, exc: PermissionDeniedError
    ) -> Response:
        return Response(
            content=f'{{"error":"forbidden","message":"{exc}"}}',
            status_code=403,
            media_type="application/json",
        )

    @app.exception_handler(ComplianceViolationError)
    async def compliance_violation_handler(
        request: Request, exc: ComplianceViolationError
    ) -> Response:
        return Response(
            content=f'{{"error":"compliance_violation","message":"{exc}"}}',
            status_code=403,
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

        try:
            result: InferenceResult = optimizer.infer(
                prompt=body.prompt,
                task_id=body.task_id,
                latency_budget_ms=body.latency_budget_ms,
                quality_threshold=body.quality_threshold,
                cost_budget=body.cost_budget,
                user_id=body.user_id,
            )
        except NoModelsAvailableError as exc:
            logger.error(
                "No models available",
                extra={"request_id": request_id, "error": str(exc)},
            )
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "service_unavailable",
                    "message": str(exc),
                    "request_id": request_id,
                },
            ) from exc
        except ProviderError as exc:
            logger.error(
                "All providers unavailable",
                extra={"request_id": request_id, "error": str(exc)},
            )
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "service_unavailable",
                    "message": str(exc),
                    "request_id": request_id,
                    "retry_after_seconds": 30,
                },
            ) from exc

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
        try:
            data = engine.cost_breakdown(period=period, group_by=group_by)  # type: ignore[arg-type]
        except ObservabilityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
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
        try:
            data = engine.trend(metric=metric, period=period, intervals=intervals)
        except ObservabilityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
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

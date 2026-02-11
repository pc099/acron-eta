"""
FastAPI REST API for Asahi inference optimizer.

Endpoints:
    POST /infer   - Run inference with smart routing and caching
    GET  /metrics - View cost/latency/quality analytics
    GET  /models  - List available models with pricing
    GET  /health  - Service health check
"""

import logging
import time
import uuid
from collections import defaultdict
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.exceptions import NoModelsAvailableError, ProviderError
from src.optimizer import InferenceOptimizer, InferenceResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request / Response Schemas
# ---------------------------------------------------------------------------


class InferRequest(BaseModel):
    """Incoming inference request body.

    Attributes:
        prompt: User query (1-100000 characters).
        task_id: Optional task identifier for tracking.
        latency_budget_ms: Maximum acceptable latency in milliseconds.
        quality_threshold: Minimum quality score (0.0-5.0).
        cost_budget: Optional maximum dollar cost for this request.
        user_id: Optional caller identity.
    """

    prompt: str = Field(
        ..., min_length=1, max_length=100000, description="User query"
    )
    task_id: Optional[str] = Field(
        default=None, description="Optional task identifier"
    )
    latency_budget_ms: int = Field(
        default=300, ge=50, le=30000, description="Max latency in ms"
    )
    quality_threshold: float = Field(
        default=3.5, ge=0.0, le=5.0, description="Min quality score"
    )
    cost_budget: Optional[float] = Field(
        default=None, ge=0.0, description="Max dollar cost"
    )
    user_id: Optional[str] = Field(
        default=None, description="Caller identity"
    )


class InferResponse(BaseModel):
    """Inference result returned to the caller.

    Attributes:
        request_id: Unique request identifier for tracing.
        response: The LLM response text.
        model_used: Selected model name.
        tokens_input: Input token count.
        tokens_output: Output token count.
        cost: Dollar cost for this request.
        latency_ms: End-to-end latency in milliseconds.
        cache_hit: Whether the result came from cache.
        routing_reason: Explanation of model choice.
    """

    request_id: str
    response: str = ""
    model_used: str = ""
    tokens_input: int = 0
    tokens_output: int = 0
    cost: float = 0.0
    latency_ms: float = 0.0
    cache_hit: bool = False
    routing_reason: str = ""


class HealthResponse(BaseModel):
    """Health check response.

    Attributes:
        status: Service health status.
        version: API version string.
        uptime_seconds: Seconds since service start.
        components: Health status of sub-components.
    """

    status: str
    version: str
    uptime_seconds: float
    components: Dict[str, str] = {}


class ErrorResponse(BaseModel):
    """Standard error body.

    Attributes:
        error: Error type identifier.
        message: Human-readable error description.
        request_id: Request ID for correlation.
    """

    error: str
    message: str
    request_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Rate limiter (simple in-memory, per-IP)
# ---------------------------------------------------------------------------


class RateLimiter:
    """Simple in-memory rate limiter using a sliding window.

    Args:
        max_requests: Maximum requests per window.
        window_seconds: Window size in seconds.
    """

    def __init__(
        self, max_requests: int = 100, window_seconds: int = 60
    ) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._requests: Dict[str, list] = defaultdict(list)

    def is_allowed(self, client_id: str) -> bool:
        """Check if a request from this client is allowed.

        Args:
            client_id: Client identifier (e.g. IP address).

        Returns:
            True if the request is within the rate limit.
        """
        now = time.time()
        window_start = now - self._window_seconds

        # Clean up old entries
        self._requests[client_id] = [
            t for t in self._requests[client_id] if t > window_start
        ]

        if len(self._requests[client_id]) >= self._max_requests:
            return False

        self._requests[client_id].append(now)
        return True


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


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
        """Run an inference request through Asahi's optimizer.

        The optimizer checks the cache, routes to the best model, executes
        inference, logs the event, and returns a structured response.
        """
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
            },
        )

    return app

"""
FastAPI application factory for Asahi inference optimizer.

Creates and configures the FastAPI app with all routes, middleware,
and shared state.
"""

import logging
import time
import uuid
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from src.api.middleware import RateLimiter
from src.api.schemas import (
    ErrorResponse,
    HealthResponse,
    InferRequest,
    InferResponse,
)
from src.core.optimizer import InferenceOptimizer, InferenceResult
from src.exceptions import NoModelsAvailableError, ProviderError

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
            },
        )

    return app

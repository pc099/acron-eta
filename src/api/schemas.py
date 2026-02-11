"""
Pydantic request/response models for the Asahi REST API.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


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
# Analytics schemas (Phase 6)
# ---------------------------------------------------------------------------


class CostBreakdownRequest(BaseModel):
    """Query parameters for cost breakdown.

    Attributes:
        period: Time window (hour, day, week, month).
        group_by: Grouping dimension.
    """

    period: str = Field(default="day", description="hour|day|week|month")
    group_by: str = Field(default="model", description="model|task_type|user|tier")


class TrendRequest(BaseModel):
    """Query parameters for trend data.

    Attributes:
        metric: Metric to trend.
        period: Time window.
        intervals: Number of data points.
    """

    metric: str = Field(default="cost", description="cost|latency|requests|cache_hit_rate")
    period: str = Field(default="day", description="hour|day|week|month")
    intervals: int = Field(default=30, ge=1, le=1000)


class ForecastRequest(BaseModel):
    """Query parameters for cost forecast.

    Attributes:
        horizon_days: Number of days to forecast.
        monthly_budget: Optional budget for risk detection.
    """

    horizon_days: int = Field(default=30, ge=1, le=365)
    monthly_budget: Optional[float] = Field(default=None, ge=0.0)


class AnalyticsResponse(BaseModel):
    """Generic analytics response wrapper.

    Attributes:
        data: The analytics result payload.
    """

    data: Any

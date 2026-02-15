"""
Pydantic request/response models for the Asahi REST API.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

RoutingMode = Literal["autopilot", "guided", "explicit"]


class InferRequest(BaseModel):
    """Incoming inference request body.

    Attributes:
        prompt: User query (1-100000 characters).
        task_id: Optional task identifier for tracking.
        latency_budget_ms: Maximum acceptable latency in milliseconds.
        quality_threshold: Minimum quality score (0.0-5.0).
        cost_budget: Optional maximum dollar cost for this request.
        user_id: Optional caller identity.
        routing_mode: Routing mode: "autopilot", "guided", or "explicit".
        quality_preference: Quality preference for GUIDED mode ("low", "medium", "high", "max").
        latency_preference: Latency preference for GUIDED mode ("low", "medium", "high").
        model_override: Model name for EXPLICIT mode.
        document_id: Optional document identifier for Tier 3 workflow decomposition.
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
    organization_id: Optional[str] = Field(
        default=None, description="Organisation ID for feature enrichment"
    )
    routing_mode: RoutingMode = Field(
        default="autopilot", description="Routing mode"
    )
    quality_preference: Optional[str] = Field(
        default=None, description="Quality preference for GUIDED mode"
    )
    latency_preference: Optional[str] = Field(
        default=None, description="Latency preference for GUIDED mode"
    )
    model_override: Optional[str] = Field(
        default=None, description="Model name for EXPLICIT mode"
    )
    document_id: Optional[str] = Field(
        default=None, description="Document ID for Tier 3 caching"
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
        cache_tier: Cache tier that served the result (1, 2, 3) or 0 for miss.
        routing_reason: Explanation of model choice.
        cost_original: Baseline cost before optimization (optional, for dashboard).
        cost_savings_percent: Percent saved vs baseline (optional, for dashboard).
        optimization_techniques: List of techniques applied (optional).
    """

    request_id: str
    response: str = ""
    model_used: str = ""
    tokens_input: int = 0
    tokens_output: int = 0
    cost: float = 0.0
    latency_ms: float = 0.0
    cache_hit: bool = False
    cache_tier: int = Field(
        default=0,
        ge=0,
        le=3,
        description="Cache tier that served (1/2/3) or 0 for miss",
    )
    routing_reason: str = ""
    cost_original: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Baseline cost before optimization (dashboard)",
    )
    cost_savings_percent: Optional[float] = Field(
        default=None,
        description="Percent saved vs baseline (dashboard)",
    )
    optimization_techniques: Optional[List[str]] = Field(
        default=None,
        description="Techniques applied (e.g. cache_tier_1, semantic_cache)",
    )


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


# ---------------------------------------------------------------------------
# OpenAI-compatible API (Phase 1 production)
# ---------------------------------------------------------------------------


class OpenAIChatMessage(BaseModel):
    """Single message in OpenAI chat format.

    Attributes:
        role: 'system', 'user', or 'assistant'.
        content: Message text.
    """

    role: Literal["system", "user", "assistant"]
    content: str = ""


class OpenAIChatRequest(BaseModel):
    """OpenAI-compatible chat completions request.

    Attributes:
        messages: Conversation history.
        model: Model ID (passed as model_override to Asahi).
        max_tokens: Maximum completion tokens.
        temperature: Sampling temperature (optional).
        stream: Whether to stream (Asahi may ignore for MVP).
    """

    messages: List[OpenAIChatMessage] = Field(
        ...,
        min_length=1,
        description="Conversation messages",
    )
    model: Optional[str] = Field(default=None, description="Model ID override")
    max_tokens: Optional[int] = Field(default=1024, ge=1, le=128000)
    temperature: Optional[float] = Field(default=1.0, ge=0.0, le=2.0)
    stream: Optional[bool] = Field(default=False)


class OpenAIChatChoice(BaseModel):
    """Single choice in OpenAI response."""

    index: int = 0
    message: OpenAIChatMessage
    finish_reason: Literal["stop", "length", "content_filter"] = "stop"


class OpenAIUsage(BaseModel):
    """Token usage in OpenAI format."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class OpenAIChatResponse(BaseModel):
    """OpenAI-compatible chat completions response.

    Attributes:
        id: Response ID (request_id).
        choices: List of completion choices.
        usage: Token usage.
        model: Model used.
    """

    id: str = ""
    choices: List[OpenAIChatChoice] = Field(default_factory=list)
    usage: OpenAIUsage = Field(default_factory=OpenAIUsage)
    model: str = ""

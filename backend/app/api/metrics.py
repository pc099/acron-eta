"""Prometheus metrics endpoint for ASAHIO platform observability.

Exports metrics in Prometheus format for scraping by Grafana Cloud,
Prometheus, or other monitoring systems.

Metrics exported:
- asahio_gateway_requests_total: Total gateway requests
- asahio_cache_hits_total: Cache hits by tier
- asahio_gateway_latency_seconds: Gateway latency histogram
- asahio_llm_cost_usd: LLM cost tracking
- asahio_circuit_breaker_state: Circuit breaker state by provider
- asahio_background_task_errors_total: Background task failures
- asahio_active_sessions: Active sessions gauge

Usage in Grafana:
- Cache hit rate: rate(asahio_cache_hits_total[5m]) / rate(asahio_gateway_requests_total[5m])
- P95 latency: histogram_quantile(0.95, asahio_gateway_latency_seconds)
- Error rate: rate(asahio_gateway_requests_total{status="error"}[5m])
"""

from fastapi import APIRouter, Response
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

router = APIRouter()

# Gateway request metrics
gateway_requests_total = Counter(
    "asahio_gateway_requests_total",
    "Total gateway requests",
    ["org_id", "agent_id", "routing_mode", "cache_hit", "status"]
)

# Cache metrics
cache_hits_total = Counter(
    "asahio_cache_hits_total",
    "Total cache hits",
    ["org_id", "tier"]  # tier = exact | semantic
)

cache_misses_total = Counter(
    "asahio_cache_misses_total",
    "Total cache misses",
    ["org_id", "dependency_level"]
)

cache_bypasses_total = Counter(
    "asahio_cache_bypasses_total",
    "Total cache bypasses",
    ["org_id", "reason"]  # reason = explicit_bypass | critical_dependency
)

# Latency metrics (histogram with buckets)
gateway_latency_seconds = Histogram(
    "asahio_gateway_latency_seconds",
    "Gateway latency in seconds",
    ["org_id", "routing_mode", "cache_tier"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)  # 5ms to 10s
)

cache_lookup_latency_seconds = Histogram(
    "asahio_cache_lookup_latency_seconds",
    "Cache lookup latency in seconds",
    ["tier"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1)  # 1ms to 100ms
)

# Cost metrics
llm_cost_usd = Counter(
    "asahio_llm_cost_usd",
    "LLM cost in USD",
    ["org_id", "model", "provider"]
)

cost_savings_usd = Counter(
    "asahio_cost_savings_usd",
    "Cost savings in USD from routing/caching",
    ["org_id", "source"]  # source = cache | routing | intervention
)

# Token metrics
tokens_processed_total = Counter(
    "asahio_tokens_processed_total",
    "Total tokens processed",
    ["org_id", "direction", "model"]  # direction = input | output
)

# Routing metrics
routing_decisions_total = Counter(
    "asahio_routing_decisions_total",
    "Total routing decisions",
    ["org_id", "routing_mode", "model_selected"]
)

routing_confidence = Histogram(
    "asahio_routing_confidence",
    "Routing confidence score",
    ["org_id", "routing_mode"],
    buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99)
)

# Intervention metrics
intervention_actions_total = Counter(
    "asahio_intervention_actions_total",
    "Total intervention actions",
    ["org_id", "intervention_mode", "action"]  # action = LOG | FLAG | AUGMENT | REROUTE | BLOCK
)

risk_scores = Histogram(
    "asahio_risk_scores",
    "Risk scores distribution",
    ["org_id"],
    buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99)
)

# Circuit breaker metrics
circuit_breaker_state = Gauge(
    "asahio_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open, 2=half_open)",
    ["provider"]
)

circuit_breaker_failures_total = Counter(
    "asahio_circuit_breaker_failures_total",
    "Total circuit breaker failures",
    ["provider"]
)

# Background task metrics
background_task_errors_total = Counter(
    "asahio_background_task_errors_total",
    "Total background task errors",
    ["task_name", "error_type"]
)

background_task_retries_total = Counter(
    "asahio_background_task_retries_total",
    "Total background task retries",
    ["task_name"]
)

# Session metrics
active_sessions = Gauge(
    "asahio_active_sessions",
    "Active sessions count",
    ["org_id"]
)

session_steps = Histogram(
    "asahio_session_steps",
    "Steps per session",
    ["org_id"],
    buckets=(1, 2, 3, 5, 10, 20, 50, 100)
)

# ABA metrics
aba_observations_total = Counter(
    "asahio_aba_observations_total",
    "Total ABA observations recorded",
    ["org_id", "agent_id"]
)

aba_hallucination_rate = Gauge(
    "asahio_aba_hallucination_rate",
    "Agent hallucination rate",
    ["org_id", "agent_id"]
)


@router.get("/metrics")
async def prometheus_metrics():
    """Export Prometheus metrics.

    Returns metrics in Prometheus text format for scraping.
    Configure your Prometheus or Grafana Cloud to scrape this endpoint.

    Example Prometheus config:
        scrape_configs:
          - job_name: 'asahio'
            scrape_interval: 15s
            static_configs:
              - targets: ['api.asahio.in']
            metrics_path: '/metrics'
            bearer_token: 'your-api-key'
    """
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )

# Phase 6: Enterprise Observability -- Component Specification

> **Status**: PLANNED  
> **Timeline**: 10 weeks  
> **Impact**: Operational visibility (no direct cost savings)  
> **Prerequisite**: Phase 2 complete (relies on tiered cache metrics)  

---

## 1. Objective

Provide complete operational visibility through real-time dashboards, cost forecasting, anomaly detection, and actionable recommendations.  Enable operations teams and customers to understand, monitor, and optimise their LLM usage.

---

## 2. Component 1: MetricsCollector

### 2.1 Purpose

Central hub that collects, aggregates, and exposes metrics from all Asahi components.  Feeds data to Prometheus for time-series storage.

### 2.2 File

`src/phase6/metrics_collector.py`

### 2.3 Public Interface

```python
class MetricsCollector:
    def __init__(self, config: MetricsConfig) -> None: ...
    
    def record_inference(self, event: InferenceEvent) -> None: ...
    def record_cache_event(self, tier: int, hit: bool, latency_ms: float) -> None: ...
    def record_routing_decision(self, mode: str, model: str, latency_ms: float) -> None: ...
    def record_batch_event(self, batch_size: int, savings_pct: float) -> None: ...
    def record_error(self, error_type: str, component: str) -> None: ...
    
    def get_prometheus_metrics(self) -> str: ...
    # Returns Prometheus text exposition format
    
    def get_summary(self, window_minutes: int = 60) -> Dict[str, Any]: ...
```

### 2.4 Prometheus Metrics Exported

| Metric Name | Type | Labels | Description |
|-------------|------|--------|-------------|
| `asahi_requests_total` | Counter | `model`, `task_type`, `cache_tier` | Total requests |
| `asahi_cost_dollars_total` | Counter | `model` | Total cost in dollars |
| `asahi_savings_dollars_total` | Counter | `phase` | Total savings |
| `asahi_latency_ms` | Histogram | `model`, `cache_tier` | Request latency distribution |
| `asahi_cache_hits_total` | Counter | `tier` | Cache hits by tier |
| `asahi_cache_misses_total` | Counter | `tier` | Cache misses by tier |
| `asahi_cache_hit_rate` | Gauge | `tier` | Rolling hit rate |
| `asahi_token_count` | Histogram | `direction` (input/output) | Token distribution |
| `asahi_quality_score` | Gauge | `model` | Rolling quality average |
| `asahi_errors_total` | Counter | `error_type`, `component` | Error counts |
| `asahi_batch_size` | Histogram | | Batch sizes |

### 2.5 Configuration

```yaml
metrics:
  enabled: true
  prometheus_port: 9090
  collection_interval_seconds: 10
  retention_hours: 168  # 7 days in-memory
  export_format: prometheus  # prometheus | json | both
```

### 2.6 Testing Requirements

- 10+ tests: metric recording, Prometheus format output, summary aggregation, windowed queries.

---

## 3. Component 2: AnalyticsEngine

### 3.1 Purpose

Run analytical queries over collected metrics: cost breakdowns, trends, comparisons, and aggregations.

### 3.2 File

`src/phase6/analytics_engine.py`

### 3.3 Public Interface

```python
class AnalyticsEngine:
    def __init__(self, collector: MetricsCollector) -> None: ...
    
    def cost_breakdown(
        self,
        period: Literal["hour", "day", "week", "month"],
        group_by: Literal["model", "task_type", "user", "tier"] = "model"
    ) -> Dict[str, float]: ...
    
    def trend(
        self,
        metric: str,
        period: str,
        intervals: int = 30
    ) -> List[Dict[str, Any]]: ...
    # Returns: [{"timestamp": ..., "value": ...}, ...]
    
    def compare_to_baseline(self) -> Dict[str, Any]: ...
    # Returns: {
    #   baseline_cost, actual_cost, savings, savings_pct,
    #   baseline_model: "gpt-4", cache_contribution_pct
    # }
    
    def top_cost_drivers(self, limit: int = 10) -> List[Dict[str, Any]]: ...
    
    def cache_performance(self) -> Dict[str, Any]: ...
    # Returns: {
    #   tier_1: {hits, misses, hit_rate, avg_latency_ms},
    #   tier_2: { ... },
    #   tier_3: { ... },
    #   overall_hit_rate
    # }
    
    def latency_percentiles(self) -> Dict[str, float]: ...
    # Returns: {p50, p75, p90, p95, p99}
```

### 3.4 Testing Requirements

- 10+ tests: cost breakdown accuracy, trend generation, baseline comparison, empty data handling.

---

## 4. Component 3: ForecastingModel

### 4.1 Purpose

Predict future costs based on historical trends.  Alert on projected budget overruns.

### 4.2 File

`src/phase6/forecasting.py`

### 4.3 Public Interface

```python
class Forecast(BaseModel):
    period: str
    predicted_cost: float
    confidence_low: float
    confidence_high: float
    trend: Literal["increasing", "decreasing", "stable"]
    warning: Optional[str]

class ForecastingModel:
    def __init__(self, analytics: AnalyticsEngine) -> None: ...
    
    def predict_cost(
        self,
        horizon_days: int = 30,
        confidence: float = 0.95
    ) -> Forecast: ...
    
    def predict_cache_hit_rate(
        self,
        horizon_days: int = 30
    ) -> Dict[str, float]: ...
    
    def detect_budget_risk(
        self,
        monthly_budget: float
    ) -> Optional[str]: ...
    # Returns warning message if projected spend > budget
```

### 4.4 Forecasting Method

- Use exponential moving average (EMA) for short-term (7-day) predictions.
- Use linear regression for 30-day projections.
- Confidence interval from historical variance.

### 4.5 Testing Requirements

- 8+ tests: increasing trend, decreasing trend, stable, budget risk detection, insufficient data handling.

---

## 5. Component 4: AnomalyDetector

### 5.1 Purpose

Detect unusual patterns in cost, latency, error rates, or cache performance.  Trigger alerts when thresholds are exceeded.

### 5.2 File

`src/phase6/anomaly_detector.py`

### 5.3 Public Interface

```python
class Anomaly(BaseModel):
    anomaly_type: str        # "cost_spike", "latency_spike", "error_rate", "cache_degradation"
    severity: Literal["warning", "critical"]
    metric_name: str
    current_value: float
    expected_value: float
    deviation_pct: float
    message: str
    detected_at: datetime

class AnomalyDetector:
    def __init__(self, analytics: AnalyticsEngine, config: AnomalyConfig) -> None: ...
    
    def check(self) -> List[Anomaly]: ...
    # Run all detectors; return any anomalies found
    
    def check_cost(self) -> Optional[Anomaly]: ...
    def check_latency(self) -> Optional[Anomaly]: ...
    def check_error_rate(self) -> Optional[Anomaly]: ...
    def check_cache_performance(self) -> Optional[Anomaly]: ...
    def check_quality(self) -> Optional[Anomaly]: ...
```

#### `AnomalyConfig` (Pydantic BaseModel)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `cost_spike_threshold` | `float` | `2.0` | Alert if cost > 2x rolling average |
| `latency_spike_threshold` | `float` | `2.0` | Alert if p95 latency > 2x rolling avg |
| `error_rate_threshold` | `float` | `0.01` | Alert if error rate > 1% |
| `cache_degradation_threshold` | `float` | `0.5` | Alert if hit rate drops > 50% from baseline |
| `quality_drop_threshold` | `float` | `0.5` | Alert if quality drops > 0.5 points |
| `rolling_window_hours` | `int` | `24` | Window for computing baselines |

### 5.4 Testing Requirements

- 10+ tests: each anomaly type detection, no false positives on normal data, severity classification, insufficient baseline data handling.

---

## 6. Component 5: RecommendationEngine

### 6.1 Purpose

Analyse usage patterns and suggest actionable optimisation improvements.

### 6.2 File

`src/phase6/recommendations.py`

### 6.3 Public Interface

```python
class Recommendation(BaseModel):
    id: str
    category: str     # "cache", "routing", "token", "model"
    title: str
    description: str
    estimated_savings: Optional[float]
    priority: Literal["low", "medium", "high"]
    action: str       # what the user should do

class RecommendationEngine:
    def __init__(self, analytics: AnalyticsEngine) -> None: ...
    def generate(self) -> List[Recommendation]: ...
```

### 6.4 Recommendation Rules

| Condition | Recommendation |
|-----------|---------------|
| Cache hit rate < 50% | "Review cache TTL settings; consider increasing" |
| Most requests go to expensive model | "Lower quality threshold for {task_type} tasks" |
| Tier 2 hit rate < 20% | "Check embedding quality or lower similarity threshold" |
| Token count variance > 50% | "Enable token optimization (Phase 4)" |
| Single model handles >80% traffic | "Expand model registry with cheaper alternatives" |

### 6.5 Testing Requirements

- 8+ tests: each recommendation rule triggers correctly.

---

## 7. Dashboard Integration

### 7.1 Grafana Dashboard Panels

| Panel | Metrics Used | Type |
|-------|-------------|------|
| Total Cost (today) | `asahi_cost_dollars_total` | Stat |
| Savings vs Baseline | `asahi_savings_dollars_total` | Stat |
| Cache Hit Rate by Tier | `asahi_cache_hit_rate` | Pie chart |
| Request Volume | `asahi_requests_total` | Time series |
| Cost Trend | `asahi_cost_dollars_total` rate | Time series |
| Latency Percentiles | `asahi_latency_ms` | Heatmap |
| Model Usage Distribution | `asahi_requests_total` by model | Bar chart |
| Error Rate | `asahi_errors_total` | Time series |

### 7.2 API Endpoints (added to REST API)

| Endpoint | Description |
|----------|-------------|
| `GET /analytics/cost-breakdown` | Cost breakdown by model/task/period |
| `GET /analytics/trends` | Time-series trend data |
| `GET /analytics/forecast` | Cost forecast |
| `GET /analytics/anomalies` | Current anomalies |
| `GET /analytics/recommendations` | Active recommendations |

---

## 8. Acceptance Criteria

- [ ] MetricsCollector exposes valid Prometheus text format
- [ ] AnalyticsEngine produces accurate cost breakdowns
- [ ] ForecastingModel predicts within 20% of actual on test data
- [ ] AnomalyDetector has zero false positives on normal traffic; catches all injected anomalies
- [ ] RecommendationEngine generates actionable suggestions
- [ ] Grafana dashboard JSON provisioned and importable
- [ ] 50+ unit tests with >90% coverage
- [ ] Analytics endpoints respond in < 100 ms

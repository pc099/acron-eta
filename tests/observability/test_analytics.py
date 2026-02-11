"""Tests for AnalyticsEngine."""

from datetime import datetime, timedelta, timezone

import pytest

from src.exceptions import ObservabilityError
from src.observability.analytics import AnalyticsEngine
from src.observability.metrics import MetricsCollector


def _seed_collector(
    collector: MetricsCollector,
    count: int = 20,
    model: str = "gpt-4-turbo",
    cost: float = 0.02,
    latency: float = 150.0,
    input_tokens: int = 100,
    output_tokens: int = 50,
    task_type: str = "summarization",
    cache_tier: str = "0",
) -> None:
    """Helper to seed a collector with identical events."""
    for _ in range(count):
        collector.record_inference({
            "model": model,
            "task_type": task_type,
            "cache_tier": cache_tier,
            "cost": cost,
            "latency_ms": latency,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "quality_score": 4.0,
        })


class TestCostBreakdown:
    """Tests for cost_breakdown."""

    @pytest.fixture
    def engine(self) -> AnalyticsEngine:
        c = MetricsCollector()
        _seed_collector(c, count=10, model="gpt-4-turbo", cost=0.05)
        _seed_collector(c, count=5, model="claude-3-5-sonnet", cost=0.01)
        return AnalyticsEngine(c)

    def test_breakdown_by_model(self, engine: AnalyticsEngine) -> None:
        """Should break down cost by model."""
        result = engine.cost_breakdown(period="day", group_by="model")
        assert "gpt-4-turbo" in result
        assert "claude-3-5-sonnet" in result
        assert result["gpt-4-turbo"] > result["claude-3-5-sonnet"]

    def test_breakdown_by_task_type(self, engine: AnalyticsEngine) -> None:
        """Should break down cost by task_type."""
        result = engine.cost_breakdown(period="day", group_by="task_type")
        assert "summarization" in result

    def test_breakdown_empty_period(self) -> None:
        """Should return empty dict when no data in period."""
        c = MetricsCollector()
        engine = AnalyticsEngine(c)
        result = engine.cost_breakdown(period="hour", group_by="model")
        assert result == {}

    def test_invalid_period_raises(self) -> None:
        """Should raise ObservabilityError for unknown period."""
        c = MetricsCollector()
        engine = AnalyticsEngine(c)
        with pytest.raises(ObservabilityError, match="Unknown period"):
            engine.cost_breakdown(period="decade", group_by="model")  # type: ignore[arg-type]

    def test_breakdown_week_period(self, engine: AnalyticsEngine) -> None:
        """Should work with week period."""
        result = engine.cost_breakdown(period="week", group_by="model")
        assert isinstance(result, dict)


class TestTrend:
    """Tests for trend."""

    @pytest.fixture
    def engine(self) -> AnalyticsEngine:
        c = MetricsCollector()
        _seed_collector(c, count=30, cost=0.02, latency=200.0)
        c.record_cache_event(tier=1, hit=True, latency_ms=0.5)
        return AnalyticsEngine(c)

    def test_cost_trend(self, engine: AnalyticsEngine) -> None:
        """Should return cost trend with correct number of intervals."""
        result = engine.trend(metric="cost", period="day", intervals=10)
        assert len(result) == 10
        assert all("timestamp" in r and "value" in r for r in result)

    def test_request_trend(self, engine: AnalyticsEngine) -> None:
        """Should return request count trend."""
        result = engine.trend(metric="requests", period="day", intervals=5)
        assert len(result) == 5
        total = sum(r["value"] for r in result)
        assert total == 30

    def test_latency_trend(self, engine: AnalyticsEngine) -> None:
        """Should return latency trend."""
        result = engine.trend(metric="latency", period="hour", intervals=5)
        assert len(result) == 5

    def test_cache_hit_rate_trend(self, engine: AnalyticsEngine) -> None:
        """Should return cache hit rate trend."""
        result = engine.trend(
            metric="cache_hit_rate", period="hour", intervals=3
        )
        assert len(result) == 3

    def test_unsupported_metric_raises(self, engine: AnalyticsEngine) -> None:
        """Should raise error for unsupported metric."""
        with pytest.raises(ObservabilityError, match="Unsupported trend metric"):
            engine.trend(metric="unicorns", period="day")


class TestCompareToBaseline:
    """Tests for compare_to_baseline."""

    @pytest.fixture
    def engine(self) -> AnalyticsEngine:
        c = MetricsCollector()
        _seed_collector(
            c,
            count=10,
            cost=0.01,
            input_tokens=100,
            output_tokens=50,
        )
        return AnalyticsEngine(c)

    def test_baseline_structure(self, engine: AnalyticsEngine) -> None:
        """Should return all expected keys."""
        result = engine.compare_to_baseline()
        assert "baseline_cost" in result
        assert "actual_cost" in result
        assert "savings" in result
        assert "savings_pct" in result
        assert "baseline_model" in result
        assert "cache_contribution_pct" in result

    def test_savings_calculation(self, engine: AnalyticsEngine) -> None:
        """Should compute savings as baseline - actual cost."""
        result = engine.compare_to_baseline()
        expected_savings = result["baseline_cost"] - result["actual_cost"]
        assert result["savings"] == pytest.approx(expected_savings, abs=0.001)

    def test_baseline_model_is_gpt4(self, engine: AnalyticsEngine) -> None:
        """Baseline model should be GPT-4."""
        result = engine.compare_to_baseline()
        assert result["baseline_model"] == "gpt-4"

    def test_empty_data(self) -> None:
        """Should return zeros for empty data."""
        engine = AnalyticsEngine(MetricsCollector())
        result = engine.compare_to_baseline()
        assert result["actual_cost"] == 0.0
        assert result["baseline_cost"] == 0.0


class TestTopCostDrivers:
    """Tests for top_cost_drivers."""

    @pytest.fixture
    def engine(self) -> AnalyticsEngine:
        c = MetricsCollector()
        _seed_collector(c, count=10, model="expensive-model", cost=0.10)
        _seed_collector(c, count=20, model="cheap-model", cost=0.005)
        return AnalyticsEngine(c)

    def test_sorted_by_cost(self, engine: AnalyticsEngine) -> None:
        """Should return drivers sorted by total cost descending."""
        result = engine.top_cost_drivers(limit=5)
        assert len(result) == 2
        assert result[0]["model"] == "expensive-model"
        assert result[0]["total_cost"] > result[1]["total_cost"]

    def test_limit_respected(self, engine: AnalyticsEngine) -> None:
        """Should respect the limit parameter."""
        result = engine.top_cost_drivers(limit=1)
        assert len(result) == 1

    def test_avg_cost_computed(self, engine: AnalyticsEngine) -> None:
        """Should compute average cost per request."""
        result = engine.top_cost_drivers()
        for driver in result:
            assert "avg_cost" in driver
            assert driver["avg_cost"] > 0


class TestCachePerformance:
    """Tests for cache_performance."""

    @pytest.fixture
    def engine(self) -> AnalyticsEngine:
        c = MetricsCollector()
        c.record_cache_event(tier=1, hit=True, latency_ms=0.5)
        c.record_cache_event(tier=1, hit=True, latency_ms=0.4)
        c.record_cache_event(tier=1, hit=False, latency_ms=0.6)
        c.record_cache_event(tier=2, hit=True, latency_ms=15.0)
        c.record_cache_event(tier=2, hit=False, latency_ms=20.0)
        return AnalyticsEngine(c)

    def test_per_tier_stats(self, engine: AnalyticsEngine) -> None:
        """Should return per-tier hit/miss/rate."""
        result = engine.cache_performance()
        assert result["tier_1"]["hits"] == 2
        assert result["tier_1"]["misses"] == 1
        assert result["tier_1"]["hit_rate"] == pytest.approx(2 / 3, abs=0.01)
        assert result["tier_2"]["hits"] == 1
        assert result["tier_2"]["misses"] == 1

    def test_overall_hit_rate(self, engine: AnalyticsEngine) -> None:
        """Should compute correct overall hit rate."""
        result = engine.cache_performance()
        # 3 hits, 2 misses -> 60%
        assert result["overall_hit_rate"] == pytest.approx(0.6, abs=0.01)

    def test_empty_cache_stats(self) -> None:
        """Should return zeros for empty cache."""
        engine = AnalyticsEngine(MetricsCollector())
        result = engine.cache_performance()
        assert result["overall_hit_rate"] == 0.0


class TestLatencyPercentiles:
    """Tests for latency_percentiles."""

    @pytest.fixture
    def engine(self) -> AnalyticsEngine:
        c = MetricsCollector()
        # Create varied latencies
        for lat in [10, 20, 30, 40, 50, 100, 200, 300, 500, 1000]:
            c.record_inference({"model": "test", "cost": 0.01, "latency_ms": lat})
        return AnalyticsEngine(c)

    def test_percentile_structure(self, engine: AnalyticsEngine) -> None:
        """Should return all standard percentiles."""
        result = engine.latency_percentiles()
        assert "p50" in result
        assert "p75" in result
        assert "p90" in result
        assert "p95" in result
        assert "p99" in result

    def test_p50_less_than_p99(self, engine: AnalyticsEngine) -> None:
        """P50 should be less than or equal to P99."""
        result = engine.latency_percentiles()
        assert result["p50"] <= result["p99"]

    def test_empty_latencies(self) -> None:
        """Should return zeros for no data."""
        engine = AnalyticsEngine(MetricsCollector())
        result = engine.latency_percentiles()
        assert result["p50"] == 0.0

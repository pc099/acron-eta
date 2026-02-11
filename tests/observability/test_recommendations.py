"""Tests for RecommendationEngine."""

from datetime import datetime, timedelta, timezone

import pytest

from src.observability.analytics import AnalyticsEngine
from src.observability.metrics import MetricsCollector, _MetricPoint
from src.observability.recommendations import (
    Recommendation,
    RecommendationConfig,
    RecommendationEngine,
)


def _seed_collector(
    collector: MetricsCollector,
    count: int = 20,
    model: str = "gpt-4-turbo",
    cost: float = 0.05,
    input_tokens: int = 100,
    output_tokens: int = 50,
    task_type: str = "summarization",
    cache_tier: str = "0",
) -> None:
    """Helper to seed a collector with events."""
    now = datetime.now(timezone.utc)
    for i in range(count):
        ts = now - timedelta(minutes=count - i)
        collector._events.append(
            _MetricPoint(
                timestamp=ts,
                value=cost,
                labels={
                    "model": model,
                    "task_type": task_type,
                    "cache_tier": cache_tier,
                    "input_tokens": str(input_tokens),
                    "output_tokens": str(output_tokens),
                    "latency_ms": "150",
                },
            )
        )
        # Also update counters for get_total_requests
        collector._requests_total[f'model="{model}"'] += 1
        collector._cost_total[f'model="{model}"'] += cost


class TestRecommendationEngineGenerate:
    """Tests for generate."""

    def test_insufficient_data_returns_empty(self) -> None:
        """Should return empty list with too few requests."""
        c = MetricsCollector()
        _seed_collector(c, count=3)
        config = RecommendationConfig(min_requests_for_analysis=10)
        engine = RecommendationEngine(AnalyticsEngine(c), config=config)
        result = engine.generate()
        assert result == []

    def test_returns_list_of_recommendations(self) -> None:
        """Should return a list of Recommendation objects."""
        c = MetricsCollector()
        _seed_collector(c, count=20, model="gpt-4-turbo", cost=0.05)
        engine = RecommendationEngine(AnalyticsEngine(c))
        result = engine.generate()
        assert isinstance(result, list)
        for rec in result:
            assert isinstance(rec, Recommendation)


class TestLowCacheHitRate:
    """Tests for _check_overall_cache rule."""

    def test_low_cache_triggers_recommendation(self) -> None:
        """Should recommend cache tuning when hit rate is low."""
        c = MetricsCollector()
        _seed_collector(c, count=20)
        # No cache hits at all -> 0% hit rate
        analytics = AnalyticsEngine(c)
        config = RecommendationConfig(min_cache_hit_rate=0.50)
        engine = RecommendationEngine(analytics, config=config)
        result = engine.generate()
        cache_recs = [r for r in result if r.category == "cache" and "Low cache hit rate" in r.title]
        assert len(cache_recs) >= 1
        assert cache_recs[0].priority == "high"

    def test_healthy_cache_no_recommendation(self) -> None:
        """Should not recommend cache tuning when hit rate is healthy."""
        c = MetricsCollector()
        _seed_collector(c, count=20)
        # High cache hit rate
        for _ in range(80):
            c.record_cache_event(tier=1, hit=True, latency_ms=0.5)
        for _ in range(20):
            c.record_cache_event(tier=1, hit=False, latency_ms=0.6)
        analytics = AnalyticsEngine(c)
        config = RecommendationConfig(min_cache_hit_rate=0.50)
        engine = RecommendationEngine(analytics, config=config)
        result = engine.generate()
        cache_recs = [r for r in result if "Low cache hit rate" in r.title]
        assert len(cache_recs) == 0


class TestLowTier2CacheHitRate:
    """Tests for _check_tier2_cache rule."""

    def test_low_tier2_triggers_recommendation(self) -> None:
        """Should recommend embedding tuning when Tier 2 hit rate is low."""
        c = MetricsCollector()
        _seed_collector(c, count=20)
        # Low tier 2 hit rate
        c.record_cache_event(tier=2, hit=True, latency_ms=15.0)
        for _ in range(10):
            c.record_cache_event(tier=2, hit=False, latency_ms=20.0)
        # Keep overall cache healthy to isolate this rule
        for _ in range(50):
            c.record_cache_event(tier=1, hit=True, latency_ms=0.5)
        analytics = AnalyticsEngine(c)
        config = RecommendationConfig(min_tier2_hit_rate=0.20)
        engine = RecommendationEngine(analytics, config=config)
        result = engine.generate()
        tier2_recs = [r for r in result if "semantic cache" in r.title.lower()]
        assert len(tier2_recs) >= 1

    def test_no_tier2_data_no_recommendation(self) -> None:
        """Should not recommend when there's no Tier 2 data."""
        c = MetricsCollector()
        _seed_collector(c, count=20)
        for _ in range(50):
            c.record_cache_event(tier=1, hit=True, latency_ms=0.5)
        analytics = AnalyticsEngine(c)
        engine = RecommendationEngine(analytics)
        result = engine.generate()
        tier2_recs = [r for r in result if "semantic cache" in r.title.lower()]
        assert len(tier2_recs) == 0


class TestExpensiveModelDominance:
    """Tests for _check_expensive_model_dominance rule."""

    def test_expensive_model_triggers_recommendation(self) -> None:
        """Should recommend routing changes for expensive dominant model."""
        c = MetricsCollector()
        _seed_collector(c, count=20, model="gpt-4-turbo", cost=0.10)
        # Keep cache healthy to isolate
        for _ in range(50):
            c.record_cache_event(tier=1, hit=True, latency_ms=0.5)
        analytics = AnalyticsEngine(c)
        engine = RecommendationEngine(analytics)
        result = engine.generate()
        routing_recs = [r for r in result if r.category == "routing"]
        assert len(routing_recs) >= 1


class TestTokenVariance:
    """Tests for _check_token_variance rule."""

    def test_high_variance_triggers_recommendation(self) -> None:
        """Should recommend token optimization when variance is high."""
        c = MetricsCollector()
        now = datetime.now(timezone.utc)
        # Mix of very small and very large prompts
        for i in range(20):
            tokens = 50 if i % 2 == 0 else 2000
            ts = now - timedelta(minutes=20 - i)
            c._events.append(
                _MetricPoint(
                    timestamp=ts,
                    value=0.02,
                    labels={
                        "model": "gpt-4-turbo",
                        "task_type": "general",
                        "cache_tier": "0",
                        "input_tokens": str(tokens),
                        "output_tokens": "50",
                        "latency_ms": "100",
                    },
                )
            )
        # Keep cache healthy
        for _ in range(50):
            c.record_cache_event(tier=1, hit=True, latency_ms=0.5)
        analytics = AnalyticsEngine(c)
        config = RecommendationConfig(
            min_requests_for_analysis=10,
            token_variance_threshold=0.50,
        )
        engine = RecommendationEngine(analytics, config=config)
        result = engine.generate()
        token_recs = [r for r in result if r.category == "token"]
        assert len(token_recs) >= 1


class TestSingleModelConcentration:
    """Tests for _check_single_model_concentration rule."""

    def test_single_model_triggers_recommendation(self) -> None:
        """Should flag when one model handles >80% of traffic."""
        c = MetricsCollector()
        _seed_collector(c, count=20, model="gpt-4-turbo", cost=0.001)
        # Add one event for another model
        _seed_collector(c, count=1, model="claude-3-5-sonnet", cost=0.001)
        # Keep cache healthy
        for _ in range(50):
            c.record_cache_event(tier=1, hit=True, latency_ms=0.5)
        analytics = AnalyticsEngine(c)
        config = RecommendationConfig(high_cost_model_traffic_pct=0.80)
        engine = RecommendationEngine(analytics, config=config)
        result = engine.generate()
        model_recs = [r for r in result if r.category == "model"]
        assert len(model_recs) >= 1

    def test_diverse_traffic_no_recommendation(self) -> None:
        """Should not flag when traffic is well-distributed."""
        c = MetricsCollector()
        _seed_collector(c, count=10, model="gpt-4-turbo", cost=0.001)
        _seed_collector(c, count=10, model="claude-3-5-sonnet", cost=0.001)
        # Keep cache healthy
        for _ in range(50):
            c.record_cache_event(tier=1, hit=True, latency_ms=0.5)
        analytics = AnalyticsEngine(c)
        config = RecommendationConfig(high_cost_model_traffic_pct=0.80)
        engine = RecommendationEngine(analytics, config=config)
        result = engine.generate()
        model_recs = [r for r in result if r.category == "model"]
        assert len(model_recs) == 0


class TestRecommendationPriority:
    """Tests for recommendation priority sorting."""

    def test_sorted_high_to_low(self) -> None:
        """Recommendations should be sorted by priority (high first)."""
        c = MetricsCollector()
        _seed_collector(c, count=20, model="gpt-4-turbo", cost=0.10)
        analytics = AnalyticsEngine(c)
        engine = RecommendationEngine(analytics)
        result = engine.generate()
        if len(result) >= 2:
            priority_order = {"high": 0, "medium": 1, "low": 2}
            for i in range(len(result) - 1):
                assert (
                    priority_order[result[i].priority]
                    <= priority_order[result[i + 1].priority]
                )


class TestRecommendationModel:
    """Tests for the Recommendation Pydantic model."""

    def test_recommendation_serialization(self) -> None:
        """Should serialize correctly."""
        rec = Recommendation(
            category="cache",
            title="Test",
            description="Test description",
            priority="high",
            action="Do something",
        )
        data = rec.model_dump()
        assert data["category"] == "cache"
        assert "id" in data
        assert len(data["id"]) == 12

    def test_recommendation_with_savings(self) -> None:
        """Should include estimated savings when provided."""
        rec = Recommendation(
            category="routing",
            title="Test",
            description="Test",
            estimated_savings=50.0,
            priority="medium",
            action="Act",
        )
        assert rec.estimated_savings == 50.0

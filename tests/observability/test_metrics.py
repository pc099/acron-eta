"""Tests for MetricsCollector."""

import time
from datetime import datetime, timedelta, timezone

import pytest

from src.exceptions import ObservabilityError
from src.observability.metrics import MetricsCollector, MetricsConfig


class TestMetricsCollectorInit:
    """Tests for MetricsCollector initialization."""

    def test_default_config(self) -> None:
        """MetricsCollector should initialize with default config."""
        collector = MetricsCollector()
        assert collector._config.enabled is True
        assert collector._config.retention_hours == 168

    def test_custom_config(self) -> None:
        """MetricsCollector should accept custom config."""
        config = MetricsConfig(enabled=False, retention_hours=24)
        collector = MetricsCollector(config=config)
        assert collector._config.enabled is False
        assert collector._config.retention_hours == 24


class TestRecordInference:
    """Tests for record_inference."""

    @pytest.fixture
    def collector(self) -> MetricsCollector:
        return MetricsCollector()

    def test_record_basic_inference(self, collector: MetricsCollector) -> None:
        """Should record a basic inference event without error."""
        collector.record_inference({
            "model": "gpt-4-turbo",
            "task_type": "summarization",
            "cache_tier": "0",
            "cost": 0.05,
            "latency_ms": 250,
            "input_tokens": 100,
            "output_tokens": 50,
            "quality_score": 4.2,
        })
        assert collector.get_total_requests() == 1
        assert collector.get_total_cost() == pytest.approx(0.05, abs=1e-6)

    def test_record_multiple_inferences(self, collector: MetricsCollector) -> None:
        """Should accumulate multiple events correctly."""
        for i in range(5):
            collector.record_inference({
                "model": "gpt-4-turbo",
                "cost": 0.01,
                "latency_ms": 100 + i * 10,
                "input_tokens": 50,
                "output_tokens": 25,
            })
        assert collector.get_total_requests() == 5
        assert collector.get_total_cost() == pytest.approx(0.05, abs=1e-6)

    def test_disabled_collector_skips(self) -> None:
        """Should not record events when disabled."""
        config = MetricsConfig(enabled=False)
        collector = MetricsCollector(config=config)
        collector.record_inference({"model": "test", "cost": 1.0})
        assert collector.get_total_requests() == 0

    def test_missing_fields_use_defaults(self, collector: MetricsCollector) -> None:
        """Should handle missing fields gracefully with defaults."""
        collector.record_inference({})
        assert collector.get_total_requests() == 1

    def test_quality_score_tracked(self, collector: MetricsCollector) -> None:
        """Should track quality scores per model."""
        collector.record_inference({
            "model": "claude-3-5-sonnet",
            "quality_score": 4.5,
            "cost": 0.01,
        })
        scores = collector.get_quality_scores()
        assert "claude-3-5-sonnet" in scores
        assert scores["claude-3-5-sonnet"] == [4.5]


class TestRecordCacheEvent:
    """Tests for record_cache_event."""

    @pytest.fixture
    def collector(self) -> MetricsCollector:
        return MetricsCollector()

    def test_cache_hit_recorded(self, collector: MetricsCollector) -> None:
        """Should increment cache hits for the given tier."""
        collector.record_cache_event(tier=1, hit=True, latency_ms=0.5)
        stats = collector.get_cache_stats()
        assert stats["1"]["hits"] == 1
        assert stats["1"]["misses"] == 0

    def test_cache_miss_recorded(self, collector: MetricsCollector) -> None:
        """Should increment cache misses for the given tier."""
        collector.record_cache_event(tier=2, hit=False, latency_ms=15.0)
        stats = collector.get_cache_stats()
        assert stats["2"]["hits"] == 0
        assert stats["2"]["misses"] == 1

    def test_hit_rate_computed(self, collector: MetricsCollector) -> None:
        """Should compute rolling hit rate correctly."""
        collector.record_cache_event(tier=1, hit=True, latency_ms=0.5)
        collector.record_cache_event(tier=1, hit=True, latency_ms=0.4)
        collector.record_cache_event(tier=1, hit=False, latency_ms=0.6)
        stats = collector.get_cache_stats()
        assert stats["1"]["hit_rate"] == pytest.approx(2 / 3, abs=0.01)


class TestRecordError:
    """Tests for record_error."""

    @pytest.fixture
    def collector(self) -> MetricsCollector:
        return MetricsCollector()

    def test_error_counted(self, collector: MetricsCollector) -> None:
        """Should increment error count for the given type/component."""
        collector.record_error("ProviderError", "routing")
        errors = collector.get_error_counts()
        assert len(errors) == 1
        assert list(errors.values())[0] == 1

    def test_multiple_error_types(self, collector: MetricsCollector) -> None:
        """Should track different error types separately."""
        collector.record_error("ProviderError", "routing")
        collector.record_error("TimeoutError", "embedding")
        collector.record_error("ProviderError", "routing")
        errors = collector.get_error_counts()
        assert len(errors) == 2


class TestRecordBatchEvent:
    """Tests for record_batch_event."""

    @pytest.fixture
    def collector(self) -> MetricsCollector:
        return MetricsCollector()

    def test_batch_recorded(self, collector: MetricsCollector) -> None:
        """Should record batch size and savings."""
        collector.record_batch_event(batch_size=5, savings_pct=15.0)
        # Verify via prometheus output
        prom = collector.get_prometheus_metrics()
        assert "asahi_batch_size" in prom


class TestRecordSavings:
    """Tests for record_savings."""

    @pytest.fixture
    def collector(self) -> MetricsCollector:
        return MetricsCollector()

    def test_savings_accumulated(self, collector: MetricsCollector) -> None:
        """Should accumulate savings across multiple records."""
        collector.record_savings("caching", 1.50)
        collector.record_savings("caching", 0.75)
        collector.record_savings("routing", 0.50)
        prom = collector.get_prometheus_metrics()
        assert "asahi_savings_dollars_total" in prom


class TestPrometheusExposition:
    """Tests for get_prometheus_metrics."""

    @pytest.fixture
    def collector(self) -> MetricsCollector:
        c = MetricsCollector()
        c.record_inference({
            "model": "gpt-4-turbo",
            "task_type": "faq",
            "cache_tier": "1",
            "cost": 0.0,
            "latency_ms": 1.0,
            "input_tokens": 50,
            "output_tokens": 0,
            "quality_score": 4.5,
        })
        c.record_cache_event(tier=1, hit=True, latency_ms=0.5)
        c.record_error("TestError", "test")
        return c

    def test_contains_help_and_type(self, collector: MetricsCollector) -> None:
        """Output should contain HELP and TYPE annotations."""
        prom = collector.get_prometheus_metrics()
        assert "# HELP asahi_requests_total" in prom
        assert "# TYPE asahi_requests_total counter" in prom

    def test_contains_counter_values(self, collector: MetricsCollector) -> None:
        """Output should contain counter metric lines."""
        prom = collector.get_prometheus_metrics()
        assert "asahi_requests_total{" in prom
        assert "asahi_cost_dollars_total{" in prom

    def test_contains_histogram_buckets(self, collector: MetricsCollector) -> None:
        """Output should contain histogram bucket lines."""
        prom = collector.get_prometheus_metrics()
        assert "asahi_latency_ms_bucket{" in prom
        assert "asahi_latency_ms_sum" in prom
        assert "asahi_latency_ms_count" in prom

    def test_contains_quality_gauge(self, collector: MetricsCollector) -> None:
        """Output should contain quality score gauge."""
        prom = collector.get_prometheus_metrics()
        assert 'asahi_quality_score{model="gpt-4-turbo"}' in prom

    def test_contains_error_counter(self, collector: MetricsCollector) -> None:
        """Output should contain error counter."""
        prom = collector.get_prometheus_metrics()
        assert "asahi_errors_total{" in prom

    def test_empty_collector_returns_valid_format(self) -> None:
        """Empty collector should return valid Prometheus format."""
        collector = MetricsCollector()
        prom = collector.get_prometheus_metrics()
        assert prom.endswith("\n")
        assert "# HELP" in prom


class TestGetSummary:
    """Tests for get_summary."""

    @pytest.fixture
    def collector(self) -> MetricsCollector:
        c = MetricsCollector()
        for _ in range(10):
            c.record_inference({
                "model": "gpt-4-turbo",
                "cost": 0.02,
                "latency_ms": 150,
                "input_tokens": 100,
                "output_tokens": 50,
            })
        return c

    def test_summary_structure(self, collector: MetricsCollector) -> None:
        """Summary should contain expected keys."""
        summary = collector.get_summary(window_minutes=60)
        assert "total_requests" in summary
        assert "total_cost" in summary
        assert "avg_latency_ms" in summary
        assert "cache_hit_rate" in summary
        assert "error_count" in summary
        assert "top_models" in summary

    def test_summary_values_correct(self, collector: MetricsCollector) -> None:
        """Summary values should match recorded data."""
        summary = collector.get_summary(window_minutes=60)
        assert summary["total_requests"] == 10
        assert summary["total_cost"] == pytest.approx(0.2, abs=0.01)

    def test_empty_window(self) -> None:
        """Summary of an empty window should return zeros."""
        collector = MetricsCollector()
        summary = collector.get_summary(window_minutes=60)
        assert summary["total_requests"] == 0
        assert summary["total_cost"] == 0.0


class TestPrune:
    """Tests for prune."""

    def test_prune_removes_old_data(self) -> None:
        """Prune should remove data older than retention window."""
        config = MetricsConfig(retention_hours=1)
        collector = MetricsCollector(config=config)

        # Inject an old event by manipulating internal state
        from src.observability.metrics import _MetricPoint
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        collector._events.append(
            _MetricPoint(timestamp=old_time, value=1.0, labels={})
        )
        collector._latency_observations.append(
            _MetricPoint(timestamp=old_time, value=100.0, labels={})
        )

        # Add a recent event
        collector.record_inference({"model": "test", "cost": 0.01})

        removed = collector.prune()
        assert removed >= 2  # old event + old latency
        assert collector.get_total_requests() == 1  # recent event kept

    def test_prune_no_old_data(self) -> None:
        """Prune with no old data should remove nothing."""
        collector = MetricsCollector()
        collector.record_inference({"model": "test", "cost": 0.01})
        removed = collector.prune()
        assert removed == 0


class TestRoutingDecision:
    """Tests for record_routing_decision."""

    def test_routing_recorded(self) -> None:
        """Should record routing decision without error."""
        collector = MetricsCollector()
        collector.record_routing_decision(
            mode="AUTOPILOT", model="claude-3-5-sonnet", latency_ms=3.5
        )
        latencies = collector.get_latency_observations()
        assert 3.5 in latencies

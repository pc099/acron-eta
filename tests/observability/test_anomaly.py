"""Tests for AnomalyDetector."""

from datetime import datetime, timedelta, timezone

import pytest

from src.observability.analytics import AnalyticsEngine
from src.observability.anomaly import Anomaly, AnomalyConfig, AnomalyDetector
from src.observability.metrics import MetricsCollector, _MetricPoint


def _seed_events(
    collector: MetricsCollector,
    count: int,
    cost: float = 0.02,
    latency: float = 150.0,
    quality: float = 4.0,
) -> None:
    """Seed events into the collector with timestamps in the last hour."""
    now = datetime.now(timezone.utc)
    for i in range(count):
        ts = now - timedelta(minutes=count - i)
        collector._events.append(
            _MetricPoint(
                timestamp=ts,
                value=cost,
                labels={
                    "model": "gpt-4-turbo",
                    "task_type": "summarization",
                    "cache_tier": "0",
                    "input_tokens": "100",
                    "output_tokens": "50",
                    "latency_ms": str(latency),
                },
            )
        )
        collector._latency_observations.append(
            _MetricPoint(timestamp=ts, value=latency, labels={})
        )
        if quality is not None:
            collector._quality_score["gpt-4-turbo"].append(quality)


class TestCheckCost:
    """Tests for check_cost."""

    def test_no_anomaly_on_normal_cost(self) -> None:
        """Should not detect anomaly when cost is normal."""
        c = MetricsCollector()
        _seed_events(c, count=50, cost=0.02)
        analytics = AnalyticsEngine(c)
        detector = AnomalyDetector(analytics)
        result = detector.check_cost()
        assert result is None

    def test_cost_spike_detected(self) -> None:
        """Should detect cost spike when recent avg is 2x+ baseline."""
        c = MetricsCollector()
        now = datetime.now(timezone.utc)

        # Old baseline events (low cost)
        for i in range(30):
            ts = now - timedelta(hours=12, minutes=i)
            c._events.append(
                _MetricPoint(timestamp=ts, value=0.01, labels={})
            )

        # Recent events (high cost)
        for i in range(10):
            ts = now - timedelta(minutes=i + 1)
            c._events.append(
                _MetricPoint(timestamp=ts, value=0.05, labels={})
            )

        analytics = AnalyticsEngine(c)
        detector = AnomalyDetector(analytics)
        result = detector.check_cost()
        assert result is not None
        assert result.anomaly_type == "cost_spike"

    def test_no_data_returns_none(self) -> None:
        """Should return None when no events exist."""
        c = MetricsCollector()
        analytics = AnalyticsEngine(c)
        detector = AnomalyDetector(analytics)
        assert detector.check_cost() is None


class TestCheckLatency:
    """Tests for check_latency."""

    def test_no_anomaly_on_normal_latency(self) -> None:
        """Should not detect anomaly when latency is normal."""
        c = MetricsCollector()
        _seed_events(c, count=20, latency=150.0)
        analytics = AnalyticsEngine(c)
        detector = AnomalyDetector(analytics)
        result = detector.check_latency()
        assert result is None

    def test_latency_spike_detected(self) -> None:
        """Should detect latency spike when p95 exceeds threshold."""
        c = MetricsCollector()
        now = datetime.now(timezone.utc)

        # Large baseline of low latencies (outside last hour but within 24h)
        # This ensures the overall p95 is low.
        for i in range(100):
            ts = now - timedelta(hours=3, minutes=i)
            c._latency_observations.append(
                _MetricPoint(timestamp=ts, value=100.0, labels={})
            )

        # Recent latencies within last hour (extremely high -- 10x)
        for i in range(10):
            ts = now - timedelta(minutes=i + 1)
            c._latency_observations.append(
                _MetricPoint(timestamp=ts, value=1000.0, labels={})
            )

        analytics = AnalyticsEngine(c)
        config = AnomalyConfig(latency_spike_threshold=2.0)
        detector = AnomalyDetector(analytics, config=config)
        result = detector.check_latency()
        assert result is not None
        assert result.anomaly_type == "latency_spike"

    def test_insufficient_data_returns_none(self) -> None:
        """Should return None with too few observations."""
        c = MetricsCollector()
        c._latency_observations.append(
            _MetricPoint(
                timestamp=datetime.now(timezone.utc),
                value=100.0,
                labels={},
            )
        )
        analytics = AnalyticsEngine(c)
        detector = AnomalyDetector(analytics)
        assert detector.check_latency() is None


class TestCheckErrorRate:
    """Tests for check_error_rate."""

    def test_no_anomaly_on_low_error_rate(self) -> None:
        """Should not detect anomaly when error rate is below threshold."""
        c = MetricsCollector()
        _seed_events(c, count=100)
        analytics = AnalyticsEngine(c)
        detector = AnomalyDetector(analytics)
        result = detector.check_error_rate()
        assert result is None

    def test_error_rate_anomaly_detected(self) -> None:
        """Should detect anomaly when error rate exceeds threshold."""
        c = MetricsCollector()
        _seed_events(c, count=10)
        # Add many errors
        for _ in range(5):
            c.record_error("ProviderError", "routing")
        analytics = AnalyticsEngine(c)
        config = AnomalyConfig(error_rate_threshold=0.01)
        detector = AnomalyDetector(analytics, config=config)
        result = detector.check_error_rate()
        assert result is not None
        assert result.anomaly_type == "error_rate"

    def test_no_requests_returns_none(self) -> None:
        """Should return None when no requests exist."""
        c = MetricsCollector()
        analytics = AnalyticsEngine(c)
        detector = AnomalyDetector(analytics)
        assert detector.check_error_rate() is None


class TestCheckCachePerformance:
    """Tests for check_cache_performance."""

    def test_no_anomaly_on_healthy_cache(self) -> None:
        """Should not detect anomaly when cache is performing well."""
        c = MetricsCollector()
        for _ in range(8):
            c.record_cache_event(tier=1, hit=True, latency_ms=0.5)
        for _ in range(2):
            c.record_cache_event(tier=1, hit=False, latency_ms=0.6)
        analytics = AnalyticsEngine(c)
        detector = AnomalyDetector(analytics)
        result = detector.check_cache_performance()
        assert result is None

    def test_cache_degradation_detected(self) -> None:
        """Should detect anomaly when cache hit rate drops significantly."""
        c = MetricsCollector()
        # Very low hit rate (below 50% baseline * degradation threshold)
        c.record_cache_event(tier=1, hit=True, latency_ms=0.5)
        for _ in range(20):
            c.record_cache_event(tier=1, hit=False, latency_ms=0.6)
        analytics = AnalyticsEngine(c)
        config = AnomalyConfig(cache_degradation_threshold=0.5)
        detector = AnomalyDetector(analytics, config=config)
        result = detector.check_cache_performance()
        assert result is not None
        assert result.anomaly_type == "cache_degradation"


class TestCheckQuality:
    """Tests for check_quality."""

    def test_no_anomaly_on_stable_quality(self) -> None:
        """Should not detect anomaly when quality is stable."""
        c = MetricsCollector()
        c._quality_score["gpt-4-turbo"] = [4.0] * 20
        analytics = AnalyticsEngine(c)
        detector = AnomalyDetector(analytics)
        result = detector.check_quality()
        assert result is None

    def test_quality_degradation_detected(self) -> None:
        """Should detect anomaly when recent quality drops."""
        c = MetricsCollector()
        # High quality early
        scores = [4.5] * 15 + [2.5] * 5  # drop in recent
        c._quality_score["gpt-4-turbo"] = scores
        analytics = AnalyticsEngine(c)
        config = AnomalyConfig(quality_drop_threshold=0.5)
        detector = AnomalyDetector(analytics, config=config)
        result = detector.check_quality()
        assert result is not None
        assert result.anomaly_type == "quality_degradation"

    def test_insufficient_quality_data(self) -> None:
        """Should return None with fewer than 5 quality scores."""
        c = MetricsCollector()
        c._quality_score["test"] = [4.0, 4.0]
        analytics = AnalyticsEngine(c)
        detector = AnomalyDetector(analytics)
        assert detector.check_quality() is None


class TestCheckAll:
    """Tests for the aggregate check method."""

    def test_check_returns_list(self) -> None:
        """Should return a list of anomalies."""
        c = MetricsCollector()
        _seed_events(c, count=20)
        analytics = AnalyticsEngine(c)
        detector = AnomalyDetector(analytics)
        result = detector.check()
        assert isinstance(result, list)

    def test_check_multiple_anomalies(self) -> None:
        """Should detect multiple anomalies at once."""
        c = MetricsCollector()
        _seed_events(c, count=10)
        # High error rate
        for _ in range(10):
            c.record_error("ProviderError", "routing")
        # Low cache
        for _ in range(20):
            c.record_cache_event(tier=1, hit=False, latency_ms=1.0)
        analytics = AnalyticsEngine(c)
        config = AnomalyConfig(error_rate_threshold=0.01)
        detector = AnomalyDetector(analytics, config=config)
        result = detector.check()
        # Should find at least error rate + cache degradation
        assert len(result) >= 2

    def test_check_empty_data(self) -> None:
        """Should return empty list with no data."""
        c = MetricsCollector()
        analytics = AnalyticsEngine(c)
        detector = AnomalyDetector(analytics)
        result = detector.check()
        assert result == []


class TestAnomalyModel:
    """Tests for the Anomaly Pydantic model."""

    def test_anomaly_serialization(self) -> None:
        """Should serialize correctly."""
        anomaly = Anomaly(
            anomaly_type="cost_spike",
            severity="warning",
            metric_name="asahi_cost_dollars_total",
            current_value=0.10,
            expected_value=0.02,
            deviation_pct=400.0,
            message="Cost spike detected",
        )
        data = anomaly.model_dump()
        assert data["anomaly_type"] == "cost_spike"
        assert data["severity"] == "warning"
        assert "detected_at" in data

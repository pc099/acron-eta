"""Tests for ForecastingModel."""

from datetime import datetime, timedelta, timezone

import pytest

from src.observability.analytics import AnalyticsEngine
from src.observability.forecasting import (
    Forecast,
    ForecastConfig,
    ForecastingModel,
)
from src.observability.metrics import MetricsCollector, _MetricPoint


def _seed_daily_costs(
    collector: MetricsCollector,
    daily_values: list,
) -> None:
    """Inject events with specific daily costs.

    Creates one event per daily value, backdated so each belongs to a
    different day.
    """
    now = datetime.now(timezone.utc)
    for i, cost in enumerate(daily_values):
        ts = now - timedelta(days=len(daily_values) - i - 1)
        collector._events.append(
            _MetricPoint(
                timestamp=ts,
                value=cost,
                labels={
                    "model": "test",
                    "task_type": "general",
                    "cache_tier": "0",
                    "input_tokens": "100",
                    "output_tokens": "50",
                    "latency_ms": "100",
                },
            )
        )


class TestPredictCost:
    """Tests for predict_cost."""

    @pytest.fixture
    def model_increasing(self) -> ForecastingModel:
        """Model with increasing daily costs."""
        c = MetricsCollector()
        _seed_daily_costs(c, [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        analytics = AnalyticsEngine(c)
        return ForecastingModel(analytics)

    @pytest.fixture
    def model_decreasing(self) -> ForecastingModel:
        """Model with decreasing daily costs."""
        c = MetricsCollector()
        _seed_daily_costs(c, [7.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.0])
        analytics = AnalyticsEngine(c)
        return ForecastingModel(analytics)

    @pytest.fixture
    def model_stable(self) -> ForecastingModel:
        """Model with stable daily costs."""
        c = MetricsCollector()
        _seed_daily_costs(c, [5.0, 5.1, 4.9, 5.0, 5.05, 4.95, 5.0])
        analytics = AnalyticsEngine(c)
        return ForecastingModel(analytics)

    def test_increasing_trend_detected(
        self, model_increasing: ForecastingModel
    ) -> None:
        """Should detect an increasing cost trend."""
        forecast = model_increasing.predict_cost(horizon_days=30)
        assert forecast.trend == "increasing"
        assert forecast.predicted_cost > 0

    def test_decreasing_trend_detected(
        self, model_decreasing: ForecastingModel
    ) -> None:
        """Should detect a decreasing cost trend."""
        forecast = model_decreasing.predict_cost(horizon_days=30)
        assert forecast.trend == "decreasing"

    def test_stable_trend_detected(
        self, model_stable: ForecastingModel
    ) -> None:
        """Should detect a stable cost trend."""
        forecast = model_stable.predict_cost(horizon_days=30)
        assert forecast.trend == "stable"

    def test_confidence_bounds(
        self, model_increasing: ForecastingModel
    ) -> None:
        """Confidence low should be <= predicted <= high."""
        forecast = model_increasing.predict_cost(
            horizon_days=30, confidence=0.95
        )
        assert forecast.confidence_low <= forecast.predicted_cost
        assert forecast.predicted_cost <= forecast.confidence_high

    def test_short_horizon_uses_ema(
        self, model_increasing: ForecastingModel
    ) -> None:
        """Short horizon should still produce a valid forecast."""
        forecast = model_increasing.predict_cost(horizon_days=3)
        assert forecast.predicted_cost > 0
        assert forecast.period == "3 days"

    def test_insufficient_data(self) -> None:
        """Should return warning when insufficient data."""
        c = MetricsCollector()
        _seed_daily_costs(c, [1.0])
        analytics = AnalyticsEngine(c)
        config = ForecastConfig(min_data_points=3)
        model = ForecastingModel(analytics, config=config)
        forecast = model.predict_cost(horizon_days=30)
        assert forecast.warning is not None
        assert "Insufficient data" in forecast.warning

    def test_increasing_trend_generates_warning(
        self, model_increasing: ForecastingModel
    ) -> None:
        """Should generate warning for increasing trend on long horizon."""
        forecast = model_increasing.predict_cost(horizon_days=30)
        assert forecast.warning is not None
        assert "trending upward" in forecast.warning


class TestPredictCacheHitRate:
    """Tests for predict_cache_hit_rate."""

    @pytest.fixture
    def model(self) -> ForecastingModel:
        c = MetricsCollector()
        c.record_cache_event(tier=1, hit=True, latency_ms=0.5)
        c.record_cache_event(tier=1, hit=True, latency_ms=0.4)
        c.record_cache_event(tier=1, hit=False, latency_ms=0.6)
        c.record_cache_event(tier=2, hit=True, latency_ms=15.0)
        analytics = AnalyticsEngine(c)
        return ForecastingModel(analytics)

    def test_returns_per_tier_rates(self, model: ForecastingModel) -> None:
        """Should return hit rates for each tier and overall."""
        result = model.predict_cache_hit_rate(horizon_days=30)
        assert "tier_1" in result
        assert "tier_2" in result
        assert "tier_3" in result
        assert "overall" in result

    def test_tier_1_rate_correct(self, model: ForecastingModel) -> None:
        """Tier 1 hit rate should be 2/3."""
        result = model.predict_cache_hit_rate()
        assert result["tier_1"] == pytest.approx(2 / 3, abs=0.01)


class TestDetectBudgetRisk:
    """Tests for detect_budget_risk."""

    @pytest.fixture
    def model(self) -> ForecastingModel:
        c = MetricsCollector()
        _seed_daily_costs(c, [10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 22.0])
        analytics = AnalyticsEngine(c)
        return ForecastingModel(analytics)

    def test_budget_exceeded_warning(self, model: ForecastingModel) -> None:
        """Should warn when projected cost exceeds budget."""
        warning = model.detect_budget_risk(monthly_budget=50.0)
        assert warning is not None
        assert "exceeds" in warning

    def test_budget_within_limit(self, model: ForecastingModel) -> None:
        """Should return None when within budget."""
        warning = model.detect_budget_risk(monthly_budget=50000.0)
        assert warning is None

    def test_insufficient_data_no_risk(self) -> None:
        """Should return None when insufficient data."""
        c = MetricsCollector()
        analytics = AnalyticsEngine(c)
        model = ForecastingModel(analytics)
        warning = model.detect_budget_risk(monthly_budget=100.0)
        assert warning is None


class TestInternalAlgorithms:
    """Tests for internal helper algorithms."""

    @pytest.fixture
    def model(self) -> ForecastingModel:
        c = MetricsCollector()
        return ForecastingModel(AnalyticsEngine(c))

    def test_ema_single_value(self, model: ForecastingModel) -> None:
        """EMA of a single value should be that value."""
        assert model._ema([5.0]) == 5.0

    def test_ema_empty(self, model: ForecastingModel) -> None:
        """EMA of empty list should be 0."""
        assert model._ema([]) == 0.0

    def test_std_dev_constant(self, model: ForecastingModel) -> None:
        """Std dev of constant values should be 0."""
        assert model._std_dev([5.0, 5.0, 5.0]) == 0.0

    def test_std_dev_single(self, model: ForecastingModel) -> None:
        """Std dev of single value should be 0."""
        assert model._std_dev([5.0]) == 0.0

    def test_linear_predict_single_value(self, model: ForecastingModel) -> None:
        """Linear predict with single value should return that value."""
        assert model._linear_predict([5.0]) == 5.0

    def test_z_score_known_values(self, model: ForecastingModel) -> None:
        """Should return correct z-scores for common confidence levels."""
        assert model._z_score(0.95) == pytest.approx(1.960, abs=0.01)
        assert model._z_score(0.99) == pytest.approx(2.576, abs=0.01)

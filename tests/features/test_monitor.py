"""Tests for FeatureMonitor -- enrichment health and impact tracking."""

import pytest

from src.features.enricher import EnrichmentResult
from src.features.monitor import FeatureMonitor, _FAILURE_THRESHOLD, _MIN_QUALITY_SAMPLES


def _make_result(
    features_available: bool = True,
    features_used: int = 3,
    latency_ms: float = 5.0,
) -> EnrichmentResult:
    """Helper to build an EnrichmentResult."""
    return EnrichmentResult(
        original_prompt="prompt",
        enriched_prompt="enriched" if features_available else "prompt",
        features_used=[f"f{i}" for i in range(features_used)] if features_available else [],
        feature_tokens_added=features_used * 5 if features_available else 0,
        enrichment_latency_ms=latency_ms,
        features_available=features_available,
    )


class TestFeatureMonitorRecording:
    """Tests for recording enrichment outcomes."""

    @pytest.fixture
    def monitor(self) -> FeatureMonitor:
        return FeatureMonitor()

    def test_record_successful_enrichment(self, monitor: FeatureMonitor) -> None:
        monitor.record_enrichment(_make_result(features_available=True))
        stats = monitor.get_stats()
        assert stats["total_enrichments"] == 1
        assert stats["successful_enrichments"] == 1
        assert stats["failed_enrichments"] == 0

    def test_record_failed_enrichment(self, monitor: FeatureMonitor) -> None:
        monitor.record_enrichment(_make_result(features_available=False))
        stats = monitor.get_stats()
        assert stats["total_enrichments"] == 1
        assert stats["successful_enrichments"] == 0
        assert stats["failed_enrichments"] == 1

    def test_avg_features_used(self, monitor: FeatureMonitor) -> None:
        monitor.record_enrichment(_make_result(features_used=2))
        monitor.record_enrichment(_make_result(features_used=4))
        stats = monitor.get_stats()
        assert stats["avg_features_used"] == 3.0

    def test_avg_latency(self, monitor: FeatureMonitor) -> None:
        monitor.record_enrichment(_make_result(latency_ms=10.0))
        monitor.record_enrichment(_make_result(latency_ms=20.0))
        stats = monitor.get_stats()
        assert stats["avg_latency_ms"] == 15.0

    def test_availability_percentage(self, monitor: FeatureMonitor) -> None:
        for _ in range(3):
            monitor.record_enrichment(_make_result(features_available=True))
        monitor.record_enrichment(_make_result(features_available=False))
        stats = monitor.get_stats()
        assert stats["feature_store_availability_pct"] == 75.0

    def test_consecutive_failures_tracked(self, monitor: FeatureMonitor) -> None:
        for _ in range(3):
            monitor.record_enrichment(_make_result(features_available=False))
        stats = monitor.get_stats()
        assert stats["consecutive_failures"] == 3

    def test_consecutive_failures_reset_on_success(
        self, monitor: FeatureMonitor
    ) -> None:
        for _ in range(3):
            monitor.record_enrichment(_make_result(features_available=False))
        monitor.record_enrichment(_make_result(features_available=True))
        stats = monitor.get_stats()
        assert stats["consecutive_failures"] == 0


class TestFeatureMonitorQuality:
    """Tests for quality tracking with/without features."""

    @pytest.fixture
    def monitor(self) -> FeatureMonitor:
        return FeatureMonitor()

    def test_quality_with_features(self, monitor: FeatureMonitor) -> None:
        monitor.record_enrichment(
            _make_result(features_available=True), inference_quality=4.5
        )
        monitor.record_enrichment(
            _make_result(features_available=True), inference_quality=4.0
        )
        stats = monitor.get_stats()
        assert stats["quality_with_features"] == 4.25

    def test_quality_without_features(self, monitor: FeatureMonitor) -> None:
        monitor.record_enrichment(
            _make_result(features_available=False), inference_quality=3.5
        )
        stats = monitor.get_stats()
        assert stats["quality_without_features"] == 3.5

    def test_quality_delta(self, monitor: FeatureMonitor) -> None:
        monitor.record_enrichment(
            _make_result(features_available=True), inference_quality=4.5
        )
        monitor.record_enrichment(
            _make_result(features_available=False), inference_quality=3.5
        )
        stats = monitor.get_stats()
        assert stats["quality_delta"] == 1.0

    def test_quality_none_when_no_data(self, monitor: FeatureMonitor) -> None:
        stats = monitor.get_stats()
        assert stats["quality_with_features"] is None
        assert stats["quality_without_features"] is None
        assert stats["quality_delta"] is None


class TestShouldEnrich:
    """Tests for the should_enrich decision logic."""

    @pytest.fixture
    def monitor(self) -> FeatureMonitor:
        return FeatureMonitor()

    def test_should_enrich_by_default(self, monitor: FeatureMonitor) -> None:
        assert monitor.should_enrich("general") is True

    def test_disabled_after_consecutive_failures(
        self, monitor: FeatureMonitor
    ) -> None:
        for _ in range(_FAILURE_THRESHOLD):
            monitor.record_enrichment(_make_result(features_available=False))
        assert monitor.should_enrich("general") is False

    def test_re_enabled_after_success(self, monitor: FeatureMonitor) -> None:
        for _ in range(_FAILURE_THRESHOLD):
            monitor.record_enrichment(_make_result(features_available=False))
        assert monitor.should_enrich("general") is False
        # One success resets the counter
        monitor.record_enrichment(_make_result(features_available=True))
        assert monitor.should_enrich("general") is True

    def test_disabled_for_high_failure_task(
        self, monitor: FeatureMonitor
    ) -> None:
        """Per-task failure rate > 50% disables enrichment."""
        for _ in range(_MIN_QUALITY_SAMPLES):
            monitor.record_task_enrichment("bad_task", success=False)
        assert monitor.should_enrich("bad_task") is False

    def test_allowed_for_low_failure_task(
        self, monitor: FeatureMonitor
    ) -> None:
        for _ in range(_MIN_QUALITY_SAMPLES):
            monitor.record_task_enrichment("good_task", success=True)
        assert monitor.should_enrich("good_task") is True

    def test_disabled_when_quality_worse_with_features(
        self, monitor: FeatureMonitor
    ) -> None:
        """If features hurt quality, enrichment should be disabled."""
        for _ in range(_MIN_QUALITY_SAMPLES):
            monitor.record_enrichment(
                _make_result(features_available=True), inference_quality=3.0
            )
        for _ in range(_MIN_QUALITY_SAMPLES):
            monitor.record_enrichment(
                _make_result(features_available=False), inference_quality=4.0
            )
        assert monitor.should_enrich("general") is False


class TestFeatureMonitorReset:
    """Tests for the reset method."""

    def test_reset_clears_all(self) -> None:
        monitor = FeatureMonitor()
        for _ in range(5):
            monitor.record_enrichment(_make_result(), inference_quality=4.0)
        monitor.reset()
        stats = monitor.get_stats()
        assert stats["total_enrichments"] == 0
        assert stats["successful_enrichments"] == 0
        assert stats["avg_features_used"] == 0.0

    def test_reset_re_enables_enrichment(self) -> None:
        monitor = FeatureMonitor()
        for _ in range(_FAILURE_THRESHOLD):
            monitor.record_enrichment(_make_result(features_available=False))
        assert monitor.should_enrich("general") is False
        monitor.reset()
        assert monitor.should_enrich("general") is True

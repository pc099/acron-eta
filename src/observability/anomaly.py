"""
AnomalyDetector -- detect unusual patterns in Asahi metrics.

Monitors cost, latency, error rates, cache performance, and quality
scores.  Compares current values against rolling baselines and raises
alerts when deviation thresholds are exceeded.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from src.exceptions import ObservabilityError
from src.observability.analytics import AnalyticsEngine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class AnomalyConfig(BaseModel):
    """Configuration for the AnomalyDetector.

    Attributes:
        cost_spike_threshold: Alert if cost > this multiple of rolling avg.
        latency_spike_threshold: Alert if p95 latency > this multiple.
        error_rate_threshold: Alert if error rate exceeds this fraction.
        cache_degradation_threshold: Alert if hit rate drops by this fraction.
        quality_drop_threshold: Alert if quality drops by this many points.
        rolling_window_hours: Window for computing baselines.
    """

    cost_spike_threshold: float = Field(default=2.0, gt=0.0)
    latency_spike_threshold: float = Field(default=2.0, gt=0.0)
    error_rate_threshold: float = Field(default=0.01, ge=0.0, le=1.0)
    cache_degradation_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    quality_drop_threshold: float = Field(default=0.5, ge=0.0)
    rolling_window_hours: int = Field(default=24, ge=1)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Anomaly(BaseModel):
    """A detected anomaly with context.

    Attributes:
        anomaly_type: Category of the anomaly.
        severity: ``warning`` or ``critical``.
        metric_name: The metric that triggered the alert.
        current_value: Observed current value.
        expected_value: Baseline / expected value.
        deviation_pct: How far the current value deviates (percentage).
        message: Human-readable description.
        detected_at: UTC timestamp of detection.
    """

    anomaly_type: str
    severity: Literal["warning", "critical"]
    metric_name: str
    current_value: float
    expected_value: float
    deviation_pct: float
    message: str
    detected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ---------------------------------------------------------------------------
# AnomalyDetector
# ---------------------------------------------------------------------------


class AnomalyDetector:
    """Detect unusual patterns in cost, latency, error, cache, and quality.

    Compares recent metrics against a rolling baseline window and
    returns any anomalies that exceed configured thresholds.

    Args:
        analytics: The AnalyticsEngine supplying metric data.
        config: Anomaly detection thresholds and window size.
    """

    def __init__(
        self,
        analytics: AnalyticsEngine,
        config: Optional[AnomalyConfig] = None,
    ) -> None:
        self._analytics = analytics
        self._config = config or AnomalyConfig()

    # ------------------------------------------------------------------
    # Aggregate check
    # ------------------------------------------------------------------

    def check(self) -> List[Anomaly]:
        """Run all anomaly detectors and return any findings.

        Returns:
            List of ``Anomaly`` objects (may be empty).
        """
        anomalies: List[Anomaly] = []

        for detector in [
            self.check_cost,
            self.check_latency,
            self.check_error_rate,
            self.check_cache_performance,
            self.check_quality,
        ]:
            try:
                result = detector()
                if result is not None:
                    anomalies.append(result)
            except Exception as exc:
                logger.error(
                    "Anomaly detector failed",
                    extra={
                        "detector": detector.__name__,
                        "error": str(exc),
                    },
                )

        if anomalies:
            logger.warning(
                "Anomalies detected",
                extra={"count": len(anomalies)},
            )
        return anomalies

    # ------------------------------------------------------------------
    # Individual detectors
    # ------------------------------------------------------------------

    def check_cost(self) -> Optional[Anomaly]:
        """Check for cost spikes.

        Compares the latest hour's average cost per request to the
        rolling baseline average.

        Returns:
            An ``Anomaly`` if cost exceeds threshold, else ``None``.
        """
        baseline_events = self._get_baseline_events()
        recent_events = self._get_recent_events()

        if not baseline_events or not recent_events:
            return None

        baseline_avg = (
            sum(e.value for e in baseline_events) / len(baseline_events)
        )
        recent_avg = (
            sum(e.value for e in recent_events) / len(recent_events)
        )

        if baseline_avg <= 0:
            return None

        ratio = recent_avg / baseline_avg
        if ratio >= self._config.cost_spike_threshold:
            deviation = (ratio - 1.0) * 100
            severity = "critical" if ratio >= self._config.cost_spike_threshold * 1.5 else "warning"
            return Anomaly(
                anomaly_type="cost_spike",
                severity=severity,
                metric_name="asahi_cost_dollars_total",
                current_value=round(recent_avg, 6),
                expected_value=round(baseline_avg, 6),
                deviation_pct=round(deviation, 2),
                message=(
                    f"Average request cost (${recent_avg:.4f}) is "
                    f"{ratio:.1f}x the baseline (${baseline_avg:.4f})."
                ),
            )

        return None

    def check_latency(self) -> Optional[Anomaly]:
        """Check for latency spikes.

        Compares p95 latency of recent observations to a baseline
        computed from older observations in the rolling window
        (excluding the most recent hour).

        Returns:
            An ``Anomaly`` if latency exceeds threshold, else ``None``.
        """
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(
            hours=self._config.rolling_window_hours
        )
        recent_start = now - timedelta(hours=1)

        # Get all observations and split into baseline (older) and recent
        all_obs = self._analytics._collector._latency_observations
        with self._analytics._collector._lock:
            all_obs_copy = list(all_obs)

        baseline_latencies = [
            o.value for o in all_obs_copy
            if window_start <= o.timestamp < recent_start
        ]
        recent_latencies = [
            o.value for o in all_obs_copy
            if o.timestamp >= recent_start
        ]

        if len(baseline_latencies) < 5 or len(recent_latencies) < 3:
            return None

        baseline_p95 = self._percentile(baseline_latencies, 95)
        recent_p95 = self._percentile(recent_latencies, 95)

        if baseline_p95 <= 0:
            return None

        ratio = recent_p95 / baseline_p95
        if ratio >= self._config.latency_spike_threshold:
            deviation = (ratio - 1.0) * 100
            severity = "critical" if ratio >= self._config.latency_spike_threshold * 1.5 else "warning"
            return Anomaly(
                anomaly_type="latency_spike",
                severity=severity,
                metric_name="asahi_latency_ms",
                current_value=round(recent_p95, 2),
                expected_value=round(baseline_p95, 2),
                deviation_pct=round(deviation, 2),
                message=(
                    f"P95 latency ({recent_p95:.0f}ms) is "
                    f"{ratio:.1f}x the baseline ({baseline_p95:.0f}ms)."
                ),
            )

        return None

    def check_error_rate(self) -> Optional[Anomaly]:
        """Check for elevated error rates.

        Computes the error rate as errors / total requests.

        Returns:
            An ``Anomaly`` if error rate exceeds threshold, else ``None``.
        """
        total_requests = self._analytics._collector.get_total_requests()
        if total_requests == 0:
            return None

        error_counts = self._analytics._collector.get_error_counts()
        total_errors = sum(error_counts.values())
        error_rate = total_errors / total_requests

        if error_rate >= self._config.error_rate_threshold:
            deviation = (
                (error_rate - self._config.error_rate_threshold)
                / max(self._config.error_rate_threshold, 0.001)
                * 100
            )
            severity = "critical" if error_rate >= self._config.error_rate_threshold * 5 else "warning"
            return Anomaly(
                anomaly_type="error_rate",
                severity=severity,
                metric_name="asahi_errors_total",
                current_value=round(error_rate, 4),
                expected_value=round(self._config.error_rate_threshold, 4),
                deviation_pct=round(deviation, 2),
                message=(
                    f"Error rate ({error_rate:.2%}) exceeds threshold "
                    f"({self._config.error_rate_threshold:.2%})."
                ),
            )

        return None

    def check_cache_performance(self) -> Optional[Anomaly]:
        """Check for cache degradation.

        Compares overall cache hit rate against a baseline expectation.

        Returns:
            An ``Anomaly`` if hit rate has degraded, else ``None``.
        """
        perf = self._analytics.cache_performance()
        overall_hit_rate = perf.get("overall_hit_rate", 0.0)

        # Check if there's any cache data at all
        total_operations = sum(
            perf.get(f"tier_{t}", {}).get("hits", 0) + perf.get(f"tier_{t}", {}).get("misses", 0)
            for t in ["1", "2", "3"]
        )
        if total_operations == 0:
            return None

        # Use a baseline expectation -- if we have prior data,
        # consider 50% as baseline.
        baseline_hit_rate = 0.5

        if baseline_hit_rate <= 0:
            return None

        drop = baseline_hit_rate - overall_hit_rate
        drop_fraction = drop / baseline_hit_rate if baseline_hit_rate > 0 else 0.0

        if drop_fraction >= self._config.cache_degradation_threshold:
            deviation = drop_fraction * 100
            severity = "critical" if drop_fraction >= 0.75 else "warning"
            return Anomaly(
                anomaly_type="cache_degradation",
                severity=severity,
                metric_name="asahi_cache_hit_rate",
                current_value=round(overall_hit_rate, 4),
                expected_value=round(baseline_hit_rate, 4),
                deviation_pct=round(deviation, 2),
                message=(
                    f"Cache hit rate ({overall_hit_rate:.1%}) has dropped "
                    f"{drop_fraction:.0%} from baseline ({baseline_hit_rate:.1%})."
                ),
            )

        return None

    def check_quality(self) -> Optional[Anomaly]:
        """Check for quality score degradation.

        Compares recent average quality to the overall average.

        Returns:
            An ``Anomaly`` if quality has dropped, else ``None``.
        """
        quality_scores = self._analytics._collector.get_quality_scores()

        all_scores: List[float] = []
        for scores in quality_scores.values():
            all_scores.extend(scores)

        if len(all_scores) < 5:
            return None

        overall_avg = sum(all_scores) / len(all_scores)

        # Recent = last 25% of observations
        recent_count = max(1, len(all_scores) // 4)
        recent_scores = all_scores[-recent_count:]
        recent_avg = sum(recent_scores) / len(recent_scores)

        drop = overall_avg - recent_avg
        if drop >= self._config.quality_drop_threshold:
            deviation = (drop / overall_avg * 100) if overall_avg > 0 else 0.0
            severity = "critical" if drop >= self._config.quality_drop_threshold * 2 else "warning"
            return Anomaly(
                anomaly_type="quality_degradation",
                severity=severity,
                metric_name="asahi_quality_score",
                current_value=round(recent_avg, 4),
                expected_value=round(overall_avg, 4),
                deviation_pct=round(deviation, 2),
                message=(
                    f"Recent quality ({recent_avg:.2f}) has dropped "
                    f"{drop:.2f} points from the average ({overall_avg:.2f})."
                ),
            )

        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_baseline_events(self) -> list:
        """Get events from the rolling baseline window.

        Returns:
            List of metric points in the baseline window.
        """
        start = datetime.now(timezone.utc) - timedelta(
            hours=self._config.rolling_window_hours
        )
        return self._analytics._collector.get_events(since=start)

    def _get_recent_events(self) -> list:
        """Get events from the last hour.

        Returns:
            List of metric points from the past 60 minutes.
        """
        start = datetime.now(timezone.utc) - timedelta(hours=1)
        return self._analytics._collector.get_events(since=start)

    @staticmethod
    def _percentile(values: List[float], pct: float) -> float:
        """Compute a percentile from a list of values.

        Args:
            values: Numeric values.
            pct: Percentile (0-100).

        Returns:
            Percentile value.
        """
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        idx = max(0, min(int(pct / 100 * len(sorted_vals)) - 1, len(sorted_vals) - 1))
        return sorted_vals[idx]

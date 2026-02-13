"""
MetricsCollector -- central hub for Asahi operational metrics.

Collects, aggregates, and exposes metrics from all Asahi components.
Provides Prometheus text exposition format output and windowed
summary queries for dashboards and analytics.
"""

import logging
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from src.config import get_settings
from src.exceptions import ObservabilityError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class MetricsConfig(BaseModel):
    """Configuration for the MetricsCollector.

    Attributes:
        enabled: Whether metrics collection is active.
        collection_interval_seconds: How often to sample gauges.
        retention_hours: How long to keep raw data points in memory.
        export_format: Output format -- ``prometheus``, ``json``, or ``both``.
    """

    enabled: bool = True
    collection_interval_seconds: int = Field(default=10, ge=1)
    retention_hours: int = Field(default=168, ge=1)
    export_format: str = Field(default="prometheus")


# ---------------------------------------------------------------------------
# Internal metric types
# ---------------------------------------------------------------------------


class _MetricPoint(BaseModel):
    """A single timestamped metric data point."""

    timestamp: datetime
    value: float
    labels: Dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# MetricsCollector
# ---------------------------------------------------------------------------


class MetricsCollector:
    """Central hub that collects, aggregates, and exposes metrics.

    Thread-safe: all mutations acquire ``_lock``.

    Args:
        config: Optional configuration; defaults are applied if omitted.
    """

    # Histogram bucket boundaries for latency and token counts
    _LATENCY_BUCKETS: List[float] = [
        5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000,
    ]
    _TOKEN_BUCKETS: List[float] = [
        10, 50, 100, 250, 500, 1000, 2500, 5000, 10000,
    ]
    _BATCH_SIZE_BUCKETS: List[float] = [1, 2, 3, 5, 8, 10, 15, 20]

    def __init__(self, config: Optional[MetricsConfig] = None) -> None:
        if config is None:
            _s = get_settings().observability
            config = MetricsConfig(
                enabled=_s.enabled,
                collection_interval_seconds=_s.collection_interval_seconds,
                retention_hours=_s.retention_hours,
                export_format=_s.export_format,
            )
        self._config = config
        self._lock = threading.Lock()

        # Counters  (label_key -> count)
        self._requests_total: Dict[str, float] = defaultdict(float)
        self._cost_total: Dict[str, float] = defaultdict(float)
        self._savings_total: Dict[str, float] = defaultdict(float)
        self._cache_hits: Dict[str, float] = defaultdict(float)
        self._cache_misses: Dict[str, float] = defaultdict(float)
        self._errors_total: Dict[str, float] = defaultdict(float)

        # Histograms  (label_key -> list of observed values)
        self._latency_observations: List[_MetricPoint] = []
        self._token_observations: List[_MetricPoint] = []
        self._batch_size_observations: List[_MetricPoint] = []

        # Gauges (rolling window data)
        self._cache_hit_rate: Dict[str, float] = {}
        self._quality_score: Dict[str, List[float]] = defaultdict(list)

        # Raw event log for windowed summaries
        self._events: List[_MetricPoint] = []

        logger.info(
            "MetricsCollector initialised",
            extra={"enabled": self._config.enabled},
        )

    # ------------------------------------------------------------------
    # Recording methods
    # ------------------------------------------------------------------

    def record_inference(self, event: Dict[str, Any]) -> None:
        """Record a complete inference event.

        Args:
            event: Dictionary with keys ``model``, ``task_type``,
                ``cache_tier`` (0 = miss), ``cost``, ``latency_ms``,
                ``input_tokens``, ``output_tokens``, ``quality_score``.

        Raises:
            ObservabilityError: If recording fails unexpectedly.
        """
        if not self._config.enabled:
            return

        try:
            model = str(event.get("model", "unknown"))
            task_type = str(event.get("task_type", "unknown"))
            cache_tier = str(event.get("cache_tier", "0"))
            cost = float(event.get("cost", 0.0))
            latency_ms = float(event.get("latency_ms", 0.0))
            input_tokens = int(event.get("input_tokens", 0))
            output_tokens = int(event.get("output_tokens", 0))
            quality = event.get("quality_score")

            now = datetime.now(timezone.utc)

            with self._lock:
                # Counters
                req_key = f'model="{model}",task_type="{task_type}",cache_tier="{cache_tier}"'
                self._requests_total[req_key] += 1
                self._cost_total[f'model="{model}"'] += cost

                # Latency histogram
                self._latency_observations.append(
                    _MetricPoint(
                        timestamp=now,
                        value=latency_ms,
                        labels={"model": model, "cache_tier": cache_tier},
                    )
                )

                # Token histograms
                self._token_observations.append(
                    _MetricPoint(
                        timestamp=now,
                        value=float(input_tokens),
                        labels={"direction": "input"},
                    )
                )
                self._token_observations.append(
                    _MetricPoint(
                        timestamp=now,
                        value=float(output_tokens),
                        labels={"direction": "output"},
                    )
                )

                # Quality gauge
                if quality is not None:
                    self._quality_score[model].append(float(quality))

                # Raw event for windowed summaries
                self._events.append(
                    _MetricPoint(
                        timestamp=now,
                        value=cost,
                        labels={
                            "model": model,
                            "task_type": task_type,
                            "cache_tier": cache_tier,
                            "latency_ms": str(latency_ms),
                            "input_tokens": str(input_tokens),
                            "output_tokens": str(output_tokens),
                        },
                    )
                )

            logger.debug(
                "Inference event recorded",
                extra={"model": model, "cost": cost},
            )

        except Exception as exc:
            raise ObservabilityError(
                f"Failed to record inference event: {exc}"
            ) from exc

    def record_cache_event(
        self, tier: int, hit: bool, latency_ms: float
    ) -> None:
        """Record a cache lookup result.

        Args:
            tier: Cache tier (1, 2, or 3).
            hit: Whether the lookup was a hit.
            latency_ms: Lookup latency in milliseconds.
        """
        if not self._config.enabled:
            return

        tier_str = str(tier)
        with self._lock:
            if hit:
                self._cache_hits[f'tier="{tier_str}"'] += 1
            else:
                self._cache_misses[f'tier="{tier_str}"'] += 1

            # Update rolling hit rate
            hits = self._cache_hits.get(f'tier="{tier_str}"', 0)
            misses = self._cache_misses.get(f'tier="{tier_str}"', 0)
            total = hits + misses
            self._cache_hit_rate[f'tier="{tier_str}"'] = (
                hits / total if total > 0 else 0.0
            )

            self._latency_observations.append(
                _MetricPoint(
                    timestamp=datetime.now(timezone.utc),
                    value=latency_ms,
                    labels={"cache_tier": tier_str},
                )
            )

        logger.debug(
            "Cache event recorded",
            extra={"tier": tier, "hit": hit, "latency_ms": latency_ms},
        )

    def record_routing_decision(
        self, mode: str, model: str, latency_ms: float
    ) -> None:
        """Record a routing decision.

        Args:
            mode: Routing mode (``AUTOPILOT``, ``GUIDED``, ``EXPLICIT``).
            model: Selected model name.
            latency_ms: Routing decision latency.
        """
        if not self._config.enabled:
            return

        with self._lock:
            key = f'model="{model}",task_type="routing",cache_tier="0"'
            self._requests_total[key] += 0  # track without double-counting
            self._latency_observations.append(
                _MetricPoint(
                    timestamp=datetime.now(timezone.utc),
                    value=latency_ms,
                    labels={"model": model, "mode": mode},
                )
            )

        logger.debug(
            "Routing decision recorded",
            extra={"mode": mode, "model": model, "latency_ms": latency_ms},
        )

    def record_batch_event(
        self, batch_size: int, savings_pct: float
    ) -> None:
        """Record a batch execution event.

        Args:
            batch_size: Number of requests in the batch.
            savings_pct: Percentage cost savings from batching.
        """
        if not self._config.enabled:
            return

        with self._lock:
            self._batch_size_observations.append(
                _MetricPoint(
                    timestamp=datetime.now(timezone.utc),
                    value=float(batch_size),
                    labels={},
                )
            )
            self._savings_total[f'phase="batching"'] += savings_pct

        logger.debug(
            "Batch event recorded",
            extra={"batch_size": batch_size, "savings_pct": savings_pct},
        )

    def record_error(self, error_type: str, component: str) -> None:
        """Record an error occurrence.

        Args:
            error_type: Error class name or category.
            component: Asahi component that raised the error.
        """
        if not self._config.enabled:
            return

        key = f'error_type="{error_type}",component="{component}"'
        with self._lock:
            self._errors_total[key] += 1

        logger.debug(
            "Error recorded",
            extra={"error_type": error_type, "component": component},
        )

    def record_savings(self, phase: str, amount: float) -> None:
        """Record dollar savings attributed to a specific phase.

        Args:
            phase: Phase name (e.g. ``caching``, ``routing``).
            amount: Dollar amount saved.
        """
        if not self._config.enabled:
            return

        with self._lock:
            self._savings_total[f'phase="{phase}"'] += amount

    # ------------------------------------------------------------------
    # Prometheus exposition
    # ------------------------------------------------------------------

    def get_prometheus_metrics(self) -> str:
        """Return all metrics in Prometheus text exposition format.

        Returns:
            Multi-line string suitable for ``/metrics`` endpoint scraping.
        """
        lines: List[str] = []

        with self._lock:
            # -- Counters --
            lines.append("# HELP asahi_requests_total Total inference requests")
            lines.append("# TYPE asahi_requests_total counter")
            for labels, val in sorted(self._requests_total.items()):
                lines.append(f"asahi_requests_total{{{labels}}} {val}")

            lines.append("# HELP asahi_cost_dollars_total Total cost in dollars")
            lines.append("# TYPE asahi_cost_dollars_total counter")
            for labels, val in sorted(self._cost_total.items()):
                lines.append(f"asahi_cost_dollars_total{{{labels}}} {val:.6f}")

            lines.append("# HELP asahi_savings_dollars_total Total savings")
            lines.append("# TYPE asahi_savings_dollars_total counter")
            for labels, val in sorted(self._savings_total.items()):
                lines.append(
                    f"asahi_savings_dollars_total{{{labels}}} {val:.6f}"
                )

            lines.append("# HELP asahi_cache_hits_total Cache hits by tier")
            lines.append("# TYPE asahi_cache_hits_total counter")
            for labels, val in sorted(self._cache_hits.items()):
                lines.append(f"asahi_cache_hits_total{{{labels}}} {val}")

            lines.append("# HELP asahi_cache_misses_total Cache misses by tier")
            lines.append("# TYPE asahi_cache_misses_total counter")
            for labels, val in sorted(self._cache_misses.items()):
                lines.append(f"asahi_cache_misses_total{{{labels}}} {val}")

            lines.append("# HELP asahi_cache_hit_rate Rolling cache hit rate")
            lines.append("# TYPE asahi_cache_hit_rate gauge")
            for labels, val in sorted(self._cache_hit_rate.items()):
                lines.append(f"asahi_cache_hit_rate{{{labels}}} {val:.4f}")

            lines.append("# HELP asahi_errors_total Error counts")
            lines.append("# TYPE asahi_errors_total counter")
            for labels, val in sorted(self._errors_total.items()):
                lines.append(f"asahi_errors_total{{{labels}}} {val}")

            # -- Histograms --
            lines.extend(
                self._format_histogram(
                    "asahi_latency_ms",
                    "Request latency distribution in ms",
                    self._latency_observations,
                    self._LATENCY_BUCKETS,
                )
            )
            lines.extend(
                self._format_histogram(
                    "asahi_token_count",
                    "Token count distribution",
                    self._token_observations,
                    self._TOKEN_BUCKETS,
                )
            )
            lines.extend(
                self._format_histogram(
                    "asahi_batch_size",
                    "Batch size distribution",
                    self._batch_size_observations,
                    self._BATCH_SIZE_BUCKETS,
                )
            )

            # -- Quality gauge --
            lines.append(
                "# HELP asahi_quality_score Rolling quality average per model"
            )
            lines.append("# TYPE asahi_quality_score gauge")
            for model, scores in sorted(self._quality_score.items()):
                if scores:
                    avg = sum(scores) / len(scores)
                    lines.append(
                        f'asahi_quality_score{{model="{model}"}} {avg:.4f}'
                    )

        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # Windowed summary
    # ------------------------------------------------------------------

    def get_summary(self, window_minutes: int = 60) -> Dict[str, Any]:
        """Return an aggregated summary over the given time window.

        Args:
            window_minutes: How many minutes of recent data to include.

        Returns:
            Dictionary with ``total_requests``, ``total_cost``,
            ``avg_latency_ms``, ``cache_hit_rate``, ``error_count``,
            and ``top_models``.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)

        with self._lock:
            window_events = [
                e for e in self._events if e.timestamp >= cutoff
            ]
            window_latencies = [
                o.value
                for o in self._latency_observations
                if o.timestamp >= cutoff
            ]
            total_errors = sum(self._errors_total.values())

        total_requests = len(window_events)
        total_cost = sum(e.value for e in window_events)
        avg_latency = (
            sum(window_latencies) / len(window_latencies)
            if window_latencies
            else 0.0
        )

        # Model distribution
        model_counts: Dict[str, int] = defaultdict(int)
        for evt in window_events:
            model_counts[evt.labels.get("model", "unknown")] += 1

        # Cache hit rate in window
        with self._lock:
            total_hits = sum(self._cache_hits.values())
            total_misses = sum(self._cache_misses.values())
        total_cache = total_hits + total_misses
        cache_hit_rate = total_hits / total_cache if total_cache > 0 else 0.0

        return {
            "window_minutes": window_minutes,
            "total_requests": total_requests,
            "total_cost": round(total_cost, 6),
            "avg_latency_ms": round(avg_latency, 2),
            "cache_hit_rate": round(cache_hit_rate, 4),
            "error_count": int(total_errors),
            "top_models": dict(
                sorted(
                    model_counts.items(),
                    key=lambda x: x[1],
                    reverse=True,
                )[:5]
            ),
        }

    # ------------------------------------------------------------------
    # Data access (for AnalyticsEngine / ForecastingModel)
    # ------------------------------------------------------------------

    def get_events(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> List[_MetricPoint]:
        """Return raw metric events, optionally filtered by time range.

        Args:
            since: Start of time window (inclusive).
            until: End of time window (inclusive).

        Returns:
            List of metric points within the requested range.
        """
        with self._lock:
            events = list(self._events)

        if since is not None:
            events = [e for e in events if e.timestamp >= since]
        if until is not None:
            events = [e for e in events if e.timestamp <= until]
        return events

    def get_latency_observations(
        self, since: Optional[datetime] = None,
    ) -> List[float]:
        """Return latency values, optionally filtered by time.

        Args:
            since: If given, only return observations after this time.

        Returns:
            List of latency values in milliseconds.
        """
        with self._lock:
            obs = list(self._latency_observations)
        if since is not None:
            obs = [o for o in obs if o.timestamp >= since]
        return [o.value for o in obs]

    def get_cache_stats(self) -> Dict[str, Dict[str, float]]:
        """Return per-tier cache statistics.

        Returns:
            Dict keyed by tier (``"1"``, ``"2"``, ``"3"``) with ``hits``,
            ``misses``, and ``hit_rate`` for each.
        """
        result: Dict[str, Dict[str, float]] = {}
        with self._lock:
            for tier in ["1", "2", "3"]:
                key = f'tier="{tier}"'
                hits = self._cache_hits.get(key, 0)
                misses = self._cache_misses.get(key, 0)
                total = hits + misses
                result[tier] = {
                    "hits": hits,
                    "misses": misses,
                    "hit_rate": hits / total if total > 0 else 0.0,
                }
        return result

    def get_error_counts(self) -> Dict[str, float]:
        """Return error counts keyed by label string.

        Returns:
            Dict mapping error label keys to counts.
        """
        with self._lock:
            return dict(self._errors_total)

    def get_total_requests(self) -> int:
        """Return total number of recorded inference events.

        Returns:
            Integer count of inference events.
        """
        with self._lock:
            return len(self._events)

    def get_total_cost(self) -> float:
        """Return total accumulated cost across all events.

        Returns:
            Sum of all recorded costs.
        """
        with self._lock:
            return sum(self._cost_total.values())

    def get_quality_scores(self) -> Dict[str, List[float]]:
        """Return per-model quality score lists.

        Returns:
            Dict mapping model name to list of quality scores.
        """
        with self._lock:
            return {k: list(v) for k, v in self._quality_score.items()}

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def prune(self) -> int:
        """Remove data points older than ``retention_hours``.

        Returns:
            Number of data points removed.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(
            hours=self._config.retention_hours
        )
        removed = 0

        with self._lock:
            before = len(self._events)
            self._events = [e for e in self._events if e.timestamp >= cutoff]
            removed += before - len(self._events)

            before = len(self._latency_observations)
            self._latency_observations = [
                o for o in self._latency_observations if o.timestamp >= cutoff
            ]
            removed += before - len(self._latency_observations)

            before = len(self._token_observations)
            self._token_observations = [
                o for o in self._token_observations if o.timestamp >= cutoff
            ]
            removed += before - len(self._token_observations)

            before = len(self._batch_size_observations)
            self._batch_size_observations = [
                o
                for o in self._batch_size_observations
                if o.timestamp >= cutoff
            ]
            removed += before - len(self._batch_size_observations)

        if removed > 0:
            logger.info(
                "Pruned old metric points",
                extra={"removed": removed, "retention_hours": self._config.retention_hours},
            )
        return removed

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_histogram(
        name: str,
        help_text: str,
        observations: List[_MetricPoint],
        buckets: List[float],
    ) -> List[str]:
        """Format observations as a Prometheus histogram.

        Args:
            name: Metric name.
            help_text: HELP annotation text.
            observations: Raw observed values.
            buckets: Histogram bucket boundaries.

        Returns:
            Lines of Prometheus text exposition.
        """
        lines: List[str] = []
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} histogram")

        if not observations:
            return lines

        values = [o.value for o in observations]
        total = sum(values)
        count = len(values)

        for bound in buckets:
            bucket_count = sum(1 for v in values if v <= bound)
            lines.append(f'{name}_bucket{{le="{bound}"}} {bucket_count}')
        lines.append(f'{name}_bucket{{le="+Inf"}} {count}')
        lines.append(f"{name}_sum {total:.6f}")
        lines.append(f"{name}_count {count}")

        return lines

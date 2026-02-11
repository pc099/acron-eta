"""
AnalyticsEngine -- analytical queries over collected Asahi metrics.

Provides cost breakdowns, time-series trends, baseline comparisons,
cache performance views, and latency percentile calculations.
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional

from src.exceptions import ObservabilityError
from src.observability.metrics import MetricsCollector

logger = logging.getLogger(__name__)


class AnalyticsEngine:
    """Run analytical queries over collected metrics.

    Consumes data from a ``MetricsCollector`` instance and produces
    structured reports for dashboards and API responses.

    Args:
        collector: The MetricsCollector to query data from.
    """

    # GPT-4 rates used for baseline cost comparison (per 1 K tokens)
    _BASELINE_INPUT_RATE_PER_K: float = 0.010
    _BASELINE_OUTPUT_RATE_PER_K: float = 0.030
    _BASELINE_MODEL: str = "gpt-4"

    def __init__(self, collector: MetricsCollector) -> None:
        self._collector = collector

    # ------------------------------------------------------------------
    # Cost breakdown
    # ------------------------------------------------------------------

    def cost_breakdown(
        self,
        period: Literal["hour", "day", "week", "month"],
        group_by: Literal["model", "task_type", "user", "tier"] = "model",
    ) -> Dict[str, float]:
        """Break down total cost by a grouping dimension.

        Args:
            period: Time window to aggregate over.
            group_by: Dimension to group by (``model``, ``task_type``,
                ``user``, or ``tier``).

        Returns:
            Dictionary mapping group key to total cost.

        Raises:
            ObservabilityError: If the period is invalid.
        """
        since = self._period_to_datetime(period)
        events = self._collector.get_events(since=since)

        breakdown: Dict[str, float] = defaultdict(float)
        for evt in events:
            key = evt.labels.get(group_by, "unknown")
            breakdown[key] += evt.value  # value == cost

        result = {
            k: round(v, 6)
            for k, v in sorted(
                breakdown.items(), key=lambda x: x[1], reverse=True
            )
        }

        logger.debug(
            "Cost breakdown computed",
            extra={"period": period, "group_by": group_by, "groups": len(result)},
        )
        return result

    # ------------------------------------------------------------------
    # Trends
    # ------------------------------------------------------------------

    def trend(
        self,
        metric: str,
        period: str,
        intervals: int = 30,
    ) -> List[Dict[str, Any]]:
        """Generate a time-series trend for a metric.

        Divides the requested ``period`` into ``intervals`` buckets and
        aggregates data points within each.

        Args:
            metric: Metric to trend -- one of ``cost``, ``latency``,
                ``requests``, ``cache_hit_rate``.
            period: Time period (``hour``, ``day``, ``week``, ``month``).
            intervals: Number of data points to return.

        Returns:
            List of dicts with ``timestamp`` (ISO string) and ``value``.

        Raises:
            ObservabilityError: If the metric name is unsupported.
        """
        supported = {"cost", "latency", "requests", "cache_hit_rate"}
        if metric not in supported:
            raise ObservabilityError(
                f"Unsupported trend metric '{metric}'. "
                f"Choose from {sorted(supported)}."
            )

        since = self._period_to_datetime(period)
        now = datetime.now(timezone.utc)
        bucket_delta = (now - since) / max(intervals, 1)

        events = self._collector.get_events(since=since)
        latencies = (
            self._collector.get_latency_observations(since=since)
            if metric == "latency"
            else []
        )

        result: List[Dict[str, Any]] = []
        for i in range(intervals):
            bucket_start = since + bucket_delta * i
            bucket_end = bucket_start + bucket_delta

            if metric == "cost":
                bucket_events = [
                    e for e in events
                    if bucket_start <= e.timestamp < bucket_end
                ]
                value = sum(e.value for e in bucket_events)

            elif metric == "requests":
                bucket_events = [
                    e for e in events
                    if bucket_start <= e.timestamp < bucket_end
                ]
                value = float(len(bucket_events))

            elif metric == "latency":
                # Use indexed latency list -- approximate by
                # proportional split since we don't have per-obs time.
                chunk_size = max(1, len(latencies) // max(intervals, 1))
                start_idx = i * chunk_size
                end_idx = start_idx + chunk_size
                chunk = latencies[start_idx:end_idx]
                value = sum(chunk) / len(chunk) if chunk else 0.0

            elif metric == "cache_hit_rate":
                cache_stats = self._collector.get_cache_stats()
                total_hits = sum(s["hits"] for s in cache_stats.values())
                total_misses = sum(s["misses"] for s in cache_stats.values())
                total = total_hits + total_misses
                value = total_hits / total if total > 0 else 0.0

            else:
                value = 0.0

            result.append({
                "timestamp": bucket_start.isoformat(),
                "value": round(value, 6),
            })

        logger.debug(
            "Trend computed",
            extra={"metric": metric, "period": period, "intervals": intervals},
        )
        return result

    # ------------------------------------------------------------------
    # Baseline comparison
    # ------------------------------------------------------------------

    def compare_to_baseline(self) -> Dict[str, Any]:
        """Compare actual cost to a GPT-4-only baseline.

        Returns:
            Dictionary with ``baseline_cost``, ``actual_cost``,
            ``savings``, ``savings_pct``, ``baseline_model``,
            and ``cache_contribution_pct``.
        """
        events = self._collector.get_events()

        actual_cost = sum(e.value for e in events)

        # Estimate baseline: every request through GPT-4
        baseline_cost = 0.0
        cache_savings = 0.0
        for evt in events:
            input_tokens = int(evt.labels.get("input_tokens", "0"))
            output_tokens = int(evt.labels.get("output_tokens", "0"))
            baseline_cost += (
                input_tokens * self._BASELINE_INPUT_RATE_PER_K
                + output_tokens * self._BASELINE_OUTPUT_RATE_PER_K
            ) / 1000

            cache_tier = evt.labels.get("cache_tier", "0")
            if cache_tier != "0":
                cache_savings += evt.value

        savings = baseline_cost - actual_cost
        savings_pct = (savings / baseline_cost * 100) if baseline_cost > 0 else 0.0
        cache_contribution = (
            (cache_savings / savings * 100) if savings > 0 else 0.0
        )

        result = {
            "baseline_cost": round(baseline_cost, 6),
            "actual_cost": round(actual_cost, 6),
            "savings": round(savings, 6),
            "savings_pct": round(savings_pct, 2),
            "baseline_model": self._BASELINE_MODEL,
            "cache_contribution_pct": round(cache_contribution, 2),
        }

        logger.info(
            "Baseline comparison computed",
            extra={"savings_pct": result["savings_pct"]},
        )
        return result

    # ------------------------------------------------------------------
    # Top cost drivers
    # ------------------------------------------------------------------

    def top_cost_drivers(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Identify the highest-cost models / task types.

        Args:
            limit: Maximum number of entries to return.

        Returns:
            List of dicts with ``model``, ``task_type``, ``total_cost``,
            ``request_count``, and ``avg_cost``.
        """
        events = self._collector.get_events()

        groups: Dict[str, Dict[str, Any]] = {}
        for evt in events:
            model = evt.labels.get("model", "unknown")
            task = evt.labels.get("task_type", "unknown")
            key = f"{model}:{task}"
            if key not in groups:
                groups[key] = {
                    "model": model,
                    "task_type": task,
                    "total_cost": 0.0,
                    "request_count": 0,
                }
            groups[key]["total_cost"] += evt.value
            groups[key]["request_count"] += 1

        for grp in groups.values():
            grp["total_cost"] = round(grp["total_cost"], 6)
            grp["avg_cost"] = round(
                grp["total_cost"] / grp["request_count"], 6
            ) if grp["request_count"] > 0 else 0.0

        sorted_groups = sorted(
            groups.values(), key=lambda g: g["total_cost"], reverse=True
        )
        return sorted_groups[:limit]

    # ------------------------------------------------------------------
    # Cache performance
    # ------------------------------------------------------------------

    def cache_performance(self) -> Dict[str, Any]:
        """Return per-tier and overall cache performance metrics.

        Returns:
            Dictionary with ``tier_1``, ``tier_2``, ``tier_3`` (each
            containing ``hits``, ``misses``, ``hit_rate``), and
            ``overall_hit_rate``.
        """
        stats = self._collector.get_cache_stats()

        result: Dict[str, Any] = {}
        total_hits = 0.0
        total_misses = 0.0

        for tier in ["1", "2", "3"]:
            tier_data = stats.get(tier, {"hits": 0, "misses": 0, "hit_rate": 0.0})
            result[f"tier_{tier}"] = {
                "hits": int(tier_data["hits"]),
                "misses": int(tier_data["misses"]),
                "hit_rate": round(tier_data["hit_rate"], 4),
            }
            total_hits += tier_data["hits"]
            total_misses += tier_data["misses"]

        total = total_hits + total_misses
        result["overall_hit_rate"] = round(
            total_hits / total if total > 0 else 0.0, 4
        )

        logger.debug(
            "Cache performance computed",
            extra={"overall_hit_rate": result["overall_hit_rate"]},
        )
        return result

    # ------------------------------------------------------------------
    # Latency percentiles
    # ------------------------------------------------------------------

    def latency_percentiles(self) -> Dict[str, float]:
        """Compute latency percentiles across all observations.

        Returns:
            Dictionary with ``p50``, ``p75``, ``p90``, ``p95``, ``p99``.
        """
        values = self._collector.get_latency_observations()

        if not values:
            return {"p50": 0.0, "p75": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0}

        sorted_vals = sorted(values)
        n = len(sorted_vals)

        def _percentile(pct: float) -> float:
            idx = max(0, min(int(pct / 100 * n) - 1, n - 1))
            return round(sorted_vals[idx], 2)

        result = {
            "p50": _percentile(50),
            "p75": _percentile(75),
            "p90": _percentile(90),
            "p95": _percentile(95),
            "p99": _percentile(99),
        }

        logger.debug(
            "Latency percentiles computed",
            extra=result,
        )
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _period_to_datetime(
        period: str,
    ) -> datetime:
        """Convert a period name to a start-of-window datetime.

        Args:
            period: One of ``hour``, ``day``, ``week``, ``month``.

        Returns:
            UTC datetime marking the start of the window.

        Raises:
            ObservabilityError: If the period is unknown.
        """
        now = datetime.now(timezone.utc)
        mapping: Dict[str, timedelta] = {
            "hour": timedelta(hours=1),
            "day": timedelta(days=1),
            "week": timedelta(weeks=1),
            "month": timedelta(days=30),
        }
        delta = mapping.get(period)
        if delta is None:
            raise ObservabilityError(
                f"Unknown period '{period}'. Choose from {sorted(mapping.keys())}."
            )
        return now - delta

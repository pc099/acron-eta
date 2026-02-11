"""
Feature monitor for Asahi inference optimizer.

Tracks feature store health, data freshness, and the impact of
enrichment on inference quality and cost.  Can automatically disable
enrichment for task types where it is not helping.
"""

import logging
import threading
from typing import Any, Dict, List, Optional

from src.features.enricher import EnrichmentResult

logger = logging.getLogger(__name__)

# After this many consecutive failures, enrichment is auto-disabled
_FAILURE_THRESHOLD = 5

# Minimum samples before quality comparison is meaningful
_MIN_QUALITY_SAMPLES = 10


class FeatureMonitor:
    """Monitor feature store health and enrichment impact.

    Thread-safe: all mutations acquire an internal lock.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

        # Counters
        self._total_enrichments: int = 0
        self._successful_enrichments: int = 0
        self._failed_enrichments: int = 0
        self._consecutive_failures: int = 0

        # Aggregate stats
        self._total_features_used: int = 0
        self._total_latency_ms: float = 0.0

        # Quality tracking (with/without enrichment)
        self._quality_with: List[float] = []
        self._quality_without: List[float] = []

        # Per-task tracking for should_enrich decisions
        self._task_failures: Dict[str, int] = {}
        self._task_enrichments: Dict[str, int] = {}

        logger.info("FeatureMonitor initialised")

    def record_enrichment(
        self,
        result: EnrichmentResult,
        inference_quality: Optional[float] = None,
    ) -> None:
        """Record the outcome of an enrichment operation.

        Args:
            result: The enrichment result to record.
            inference_quality: Optional quality score of the LLM output
                (0.0 -- 5.0).  Used to compare quality with vs. without
                feature enrichment.
        """
        with self._lock:
            self._total_enrichments += 1

            if result.features_available:
                self._successful_enrichments += 1
                self._consecutive_failures = 0
                self._total_features_used += len(result.features_used)
                self._total_latency_ms += result.enrichment_latency_ms

                if inference_quality is not None:
                    self._quality_with.append(inference_quality)
            else:
                self._failed_enrichments += 1
                self._consecutive_failures += 1

                if inference_quality is not None:
                    self._quality_without.append(inference_quality)

        logger.debug(
            "Enrichment recorded",
            extra={
                "features_available": result.features_available,
                "features_used": len(result.features_used),
                "latency_ms": result.enrichment_latency_ms,
            },
        )

    def record_task_enrichment(
        self,
        task_type: str,
        success: bool,
    ) -> None:
        """Record a per-task enrichment outcome.

        Args:
            task_type: The task type that was enriched.
            success: Whether features were available and used.
        """
        with self._lock:
            self._task_enrichments[task_type] = (
                self._task_enrichments.get(task_type, 0) + 1
            )
            if not success:
                self._task_failures[task_type] = (
                    self._task_failures.get(task_type, 0) + 1
                )

    def get_stats(self) -> Dict[str, Any]:
        """Return aggregate monitoring statistics.

        Returns:
            Dict with keys: ``total_enrichments``,
            ``successful_enrichments``, ``failed_enrichments``,
            ``avg_features_used``, ``avg_latency_ms``,
            ``quality_with_features``, ``quality_without_features``,
            ``quality_delta``, ``feature_store_availability_pct``,
            ``consecutive_failures``.
        """
        with self._lock:
            total = self._total_enrichments
            successful = self._successful_enrichments

            avg_features = (
                self._total_features_used / successful
                if successful > 0
                else 0.0
            )
            avg_latency = (
                self._total_latency_ms / successful
                if successful > 0
                else 0.0
            )
            availability = (
                (successful / total) * 100 if total > 0 else 100.0
            )

            quality_with = (
                sum(self._quality_with) / len(self._quality_with)
                if self._quality_with
                else None
            )
            quality_without = (
                sum(self._quality_without) / len(self._quality_without)
                if self._quality_without
                else None
            )
            quality_delta = (
                round(quality_with - quality_without, 3)
                if quality_with is not None and quality_without is not None
                else None
            )

        return {
            "total_enrichments": total,
            "successful_enrichments": successful,
            "failed_enrichments": self._failed_enrichments,
            "avg_features_used": round(avg_features, 2),
            "avg_latency_ms": round(avg_latency, 2),
            "quality_with_features": (
                round(quality_with, 3) if quality_with is not None else None
            ),
            "quality_without_features": (
                round(quality_without, 3) if quality_without is not None else None
            ),
            "quality_delta": quality_delta,
            "feature_store_availability_pct": round(availability, 1),
            "consecutive_failures": self._consecutive_failures,
        }

    def should_enrich(self, task_type: str) -> bool:
        """Decide whether enrichment should be attempted for a task type.

        Returns ``False`` if:
        - The feature store has had too many consecutive failures.
        - The task type has a high failure rate (>50% of attempts).
        - Quality data shows enrichment is not helping for this task.

        Args:
            task_type: The task type to check.

        Returns:
            ``True`` if enrichment is recommended.
        """
        with self._lock:
            # Global circuit breaker
            if self._consecutive_failures >= _FAILURE_THRESHOLD:
                logger.warning(
                    "Enrichment disabled: too many consecutive failures",
                    extra={
                        "consecutive_failures": self._consecutive_failures,
                        "threshold": _FAILURE_THRESHOLD,
                    },
                )
                return False

            # Per-task failure rate
            task_total = self._task_enrichments.get(task_type, 0)
            task_failures = self._task_failures.get(task_type, 0)
            if task_total >= _MIN_QUALITY_SAMPLES:
                failure_rate = task_failures / task_total
                if failure_rate > 0.5:
                    logger.info(
                        "Enrichment disabled for task: high failure rate",
                        extra={
                            "task_type": task_type,
                            "failure_rate": round(failure_rate, 2),
                        },
                    )
                    return False

            # Quality check: if enrichment is hurting quality, disable
            if (
                len(self._quality_with) >= _MIN_QUALITY_SAMPLES
                and len(self._quality_without) >= _MIN_QUALITY_SAMPLES
            ):
                avg_with = sum(self._quality_with) / len(self._quality_with)
                avg_without = (
                    sum(self._quality_without) / len(self._quality_without)
                )
                if avg_with < avg_without:
                    logger.info(
                        "Enrichment disabled: quality is worse with features",
                        extra={
                            "avg_with": round(avg_with, 3),
                            "avg_without": round(avg_without, 3),
                        },
                    )
                    return False

        return True

    def reset(self) -> None:
        """Reset all monitoring counters.

        Useful for testing or periodic resets.
        """
        with self._lock:
            self._total_enrichments = 0
            self._successful_enrichments = 0
            self._failed_enrichments = 0
            self._consecutive_failures = 0
            self._total_features_used = 0
            self._total_latency_ms = 0.0
            self._quality_with.clear()
            self._quality_without.clear()
            self._task_failures.clear()
            self._task_enrichments.clear()

        logger.info("FeatureMonitor reset")

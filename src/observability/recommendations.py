"""
RecommendationEngine -- actionable optimization suggestions for Asahi.

Analyses usage patterns from the AnalyticsEngine and generates
prioritised recommendations for cost reduction, cache tuning, and
model selection improvements.
"""

import logging
import uuid
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from src.observability.analytics import AnalyticsEngine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class RecommendationConfig(BaseModel):
    """Configuration for the RecommendationEngine.

    Attributes:
        min_cache_hit_rate: Below this overall hit rate, suggest tuning.
        min_tier2_hit_rate: Below this Tier 2 hit rate, suggest embedding.
        high_cost_model_traffic_pct: If a single model handles more than
            this fraction of traffic, suggest diversifying.
        token_variance_threshold: If token count variance exceeds this
            ratio, suggest token optimization.
        min_requests_for_analysis: Minimum events before generating recs.
    """

    min_cache_hit_rate: float = Field(default=0.50, ge=0.0, le=1.0)
    min_tier2_hit_rate: float = Field(default=0.20, ge=0.0, le=1.0)
    high_cost_model_traffic_pct: float = Field(default=0.80, ge=0.0, le=1.0)
    token_variance_threshold: float = Field(default=0.50, ge=0.0)
    min_requests_for_analysis: int = Field(default=10, ge=1)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Recommendation(BaseModel):
    """A single actionable recommendation.

    Attributes:
        id: Unique identifier.
        category: Area of optimization.
        title: Short summary.
        description: Detailed explanation.
        estimated_savings: Estimated dollar savings (if calculable).
        priority: Urgency level.
        action: What the user should do.
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    category: str
    title: str
    description: str
    estimated_savings: Optional[float] = None
    priority: Literal["low", "medium", "high"]
    action: str


# ---------------------------------------------------------------------------
# RecommendationEngine
# ---------------------------------------------------------------------------


class RecommendationEngine:
    """Analyse usage patterns and suggest optimisation improvements.

    Evaluates metrics from the ``AnalyticsEngine`` against configurable
    thresholds and produces a prioritised list of ``Recommendation``
    objects.

    Args:
        analytics: The AnalyticsEngine supplying metric data.
        config: Thresholds for recommendation rules.
    """

    def __init__(
        self,
        analytics: AnalyticsEngine,
        config: Optional[RecommendationConfig] = None,
    ) -> None:
        self._analytics = analytics
        self._config = config or RecommendationConfig()

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def generate(self) -> List[Recommendation]:
        """Run all recommendation rules and return findings.

        Returns:
            Sorted list of ``Recommendation`` objects (highest priority
            first).
        """
        total_requests = self._analytics._collector.get_total_requests()
        if total_requests < self._config.min_requests_for_analysis:
            logger.debug(
                "Not enough data for recommendations",
                extra={
                    "total_requests": total_requests,
                    "min_required": self._config.min_requests_for_analysis,
                },
            )
            return []

        recs: List[Recommendation] = []

        for rule in [
            self._check_overall_cache,
            self._check_tier2_cache,
            self._check_expensive_model_dominance,
            self._check_token_variance,
            self._check_single_model_concentration,
        ]:
            try:
                result = rule()
                if result is not None:
                    recs.append(result)
            except Exception as exc:
                logger.error(
                    "Recommendation rule failed",
                    extra={"rule": rule.__name__, "error": str(exc)},
                )

        # Sort by priority (high -> medium -> low)
        priority_order = {"high": 0, "medium": 1, "low": 2}
        recs.sort(key=lambda r: priority_order.get(r.priority, 99))

        logger.info(
            "Recommendations generated",
            extra={"count": len(recs)},
        )
        return recs

    # ------------------------------------------------------------------
    # Individual rules
    # ------------------------------------------------------------------

    def _check_overall_cache(self) -> Optional[Recommendation]:
        """Check if overall cache hit rate is too low.

        Returns:
            A recommendation if hit rate is below threshold.
        """
        perf = self._analytics.cache_performance()
        overall = perf.get("overall_hit_rate", 0.0)

        if overall < self._config.min_cache_hit_rate:
            # Estimate savings from improving cache
            baseline = self._analytics.compare_to_baseline()
            potential_savings = baseline.get("actual_cost", 0.0) * 0.3

            return Recommendation(
                category="cache",
                title="Low cache hit rate",
                description=(
                    f"Overall cache hit rate is {overall:.1%}, below the "
                    f"{self._config.min_cache_hit_rate:.0%} target. "
                    f"Increasing cache TTL or broadening the cache key "
                    f"strategy could improve hit rates."
                ),
                estimated_savings=round(potential_savings, 2) if potential_savings > 0 else None,
                priority="high",
                action=(
                    "Review cache TTL settings in config.yaml and consider "
                    "increasing cache.ttl_seconds. Evaluate whether prompt "
                    "normalisation could merge similar queries."
                ),
            )

        return None

    def _check_tier2_cache(self) -> Optional[Recommendation]:
        """Check if Tier 2 (semantic) cache hit rate is too low.

        Returns:
            A recommendation if Tier 2 hit rate is below threshold.
        """
        perf = self._analytics.cache_performance()
        tier2 = perf.get("tier_2", {})
        hits = tier2.get("hits", 0)
        misses = tier2.get("misses", 0)
        total = hits + misses

        if total == 0:
            return None

        hit_rate = hits / total
        if hit_rate < self._config.min_tier2_hit_rate:
            return Recommendation(
                category="cache",
                title="Low semantic cache hit rate",
                description=(
                    f"Tier 2 (semantic) cache hit rate is {hit_rate:.1%}, "
                    f"below the {self._config.min_tier2_hit_rate:.0%} target. "
                    f"Embedding quality or the similarity threshold may need "
                    f"adjustment."
                ),
                estimated_savings=None,
                priority="medium",
                action=(
                    "Check embedding quality by reviewing semantic cache "
                    "match scores. Consider lowering the similarity threshold "
                    "or upgrading the embedding model."
                ),
            )

        return None

    def _check_expensive_model_dominance(self) -> Optional[Recommendation]:
        """Check if most traffic goes to expensive models.

        Returns:
            A recommendation if the most expensive model handles too
            much traffic.
        """
        drivers = self._analytics.top_cost_drivers(limit=5)
        if not drivers:
            return None

        total_requests = self._analytics._collector.get_total_requests()
        if total_requests == 0:
            return None

        # Find the top cost driver
        top = drivers[0]
        top_fraction = top["request_count"] / total_requests

        # Check if the top model is expensive (avg cost > $0.01 per request)
        avg_cost = top.get("avg_cost", 0.0)
        if avg_cost > 0.01 and top_fraction > 0.3:
            estimated_savings = top["total_cost"] * 0.4  # 40% reduction possible

            return Recommendation(
                category="routing",
                title=f"High cost model '{top['model']}' handles many requests",
                description=(
                    f"Model '{top['model']}' handles "
                    f"{top['request_count']} requests "
                    f"({top_fraction:.0%} of traffic) at an average cost "
                    f"of ${avg_cost:.4f}/request. Lowering the quality "
                    f"threshold for '{top['task_type']}' tasks could route "
                    f"some of these to cheaper models."
                ),
                estimated_savings=round(estimated_savings, 2),
                priority="high",
                action=(
                    f"Lower quality_threshold for '{top['task_type']}' tasks "
                    f"in routing config, or add cheaper model alternatives "
                    f"to the model registry."
                ),
            )

        return None

    def _check_token_variance(self) -> Optional[Recommendation]:
        """Check if token counts have high variance, suggesting optimization.

        Returns:
            A recommendation if token variance is high.
        """
        events = self._analytics._collector.get_events()
        if len(events) < self._config.min_requests_for_analysis:
            return None

        token_counts = []
        for evt in events:
            input_tokens = int(evt.labels.get("input_tokens", "0"))
            if input_tokens > 0:
                token_counts.append(input_tokens)

        if len(token_counts) < 5:
            return None

        mean = sum(token_counts) / len(token_counts)
        if mean <= 0:
            return None

        variance = sum((t - mean) ** 2 for t in token_counts) / len(token_counts)
        std_dev = variance ** 0.5
        cv = std_dev / mean  # coefficient of variation

        if cv > self._config.token_variance_threshold:
            return Recommendation(
                category="token",
                title="High token count variance",
                description=(
                    f"Input token counts have a coefficient of variation "
                    f"of {cv:.2f} (mean: {mean:.0f}, std: {std_dev:.0f}). "
                    f"This suggests some prompts are significantly larger "
                    f"than others and may benefit from compression."
                ),
                estimated_savings=None,
                priority="medium",
                action=(
                    "Enable token optimization (Phase 4) to compress "
                    "large prompts. Review prompts with >2x the average "
                    "token count for unnecessary context."
                ),
            )

        return None

    def _check_single_model_concentration(self) -> Optional[Recommendation]:
        """Check if a single model handles >80% of all traffic.

        Returns:
            A recommendation if model concentration is too high.
        """
        events = self._analytics._collector.get_events()
        if not events:
            return None

        model_counts: Dict[str, int] = {}
        for evt in events:
            model = evt.labels.get("model", "unknown")
            model_counts[model] = model_counts.get(model, 0) + 1

        total = sum(model_counts.values())
        if total == 0:
            return None

        for model, count in model_counts.items():
            fraction = count / total
            if fraction > self._config.high_cost_model_traffic_pct:
                return Recommendation(
                    category="model",
                    title=f"Model '{model}' handles {fraction:.0%} of traffic",
                    description=(
                        f"A single model ('{model}') handles "
                        f"{fraction:.0%} of all traffic. This creates a "
                        f"single point of failure and may not be cost-optimal "
                        f"for all task types."
                    ),
                    estimated_savings=None,
                    priority="low",
                    action=(
                        "Expand the model registry with cheaper alternatives "
                        "for simpler tasks. Consider adding task-type-specific "
                        "routing rules."
                    ),
                )

        return None

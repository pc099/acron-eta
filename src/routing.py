"""
Routing engine for Asahi inference optimizer.

Given a set of constraints (minimum quality, maximum latency, optional
cost budget), selects the most cost-efficient model from the registry
using a filter-score-select algorithm.
"""

import logging
from typing import List, Optional, Tuple

from pydantic import BaseModel, Field

from src.exceptions import NoModelsAvailableError
from src.models import ModelProfile, ModelRegistry, calculate_cost, estimate_tokens

logger = logging.getLogger(__name__)


class RoutingConstraints(BaseModel):
    """Constraints the router must satisfy when selecting a model.

    Attributes:
        quality_threshold: Minimum acceptable quality score.
        latency_budget_ms: Maximum acceptable average latency in ms.
        cost_budget: Maximum dollar cost per request (if provided).
    """

    quality_threshold: float = Field(default=3.5, ge=0.0, le=5.0)
    latency_budget_ms: int = Field(default=300, ge=1)
    cost_budget: Optional[float] = Field(default=None, ge=0.0)


class RoutingDecision(BaseModel):
    """The outcome of a routing decision.

    Attributes:
        model_name: The selected model's canonical name.
        score: Computed quality/cost score used for ranking.
        reason: Human-readable explanation of the decision.
        candidates_evaluated: Number of models that passed the filter.
        fallback_used: True if no model passed filters and the router
            fell back to the highest-quality model.
    """

    model_name: str
    score: float = 0.0
    reason: str = ""
    candidates_evaluated: int = 0
    fallback_used: bool = False


class Router:
    """Routes inference requests to the optimal model.

    Uses a filter-score-select algorithm:
    1. **Filter**: Remove models that do not meet quality, latency,
       and (optional) cost constraints.
    2. **Score**: Compute ``quality_score / avg_cost`` for each candidate.
    3. **Select**: Pick the candidate with the highest score (best value).

    Args:
        registry: The model registry to query for available models.
    """

    def __init__(self, registry: ModelRegistry) -> None:
        self._registry = registry

    def select_model(self, constraints: RoutingConstraints) -> RoutingDecision:
        """Select the optimal model for the given constraints.

        Args:
            constraints: Quality, latency, and cost requirements.

        Returns:
            A RoutingDecision describing the selected model.

        Raises:
            NoModelsAvailableError: If the registry is empty.
        """
        all_models = self._registry.all()
        if not all_models:
            raise NoModelsAvailableError("Registry contains zero models")

        candidates = self._filter(constraints)

        if not candidates:
            logger.warning(
                "No models pass constraints; falling back to highest quality",
                extra={
                    "quality_threshold": constraints.quality_threshold,
                    "latency_budget_ms": constraints.latency_budget_ms,
                    "cost_budget": constraints.cost_budget,
                },
            )
            best = max(all_models, key=lambda m: m.quality_score)
            return RoutingDecision(
                model_name=best.name,
                score=0.0,
                reason=(
                    f"Fallback to {best.name}: no models met constraints "
                    f"(quality>={constraints.quality_threshold}, "
                    f"latency<={constraints.latency_budget_ms}ms)"
                ),
                candidates_evaluated=0,
                fallback_used=True,
            )

        scored = self._score(candidates)
        best_model, best_score = self._select(scored)

        return RoutingDecision(
            model_name=best_model.name,
            score=round(best_score, 4),
            reason=(
                f"Best quality/cost ratio among {len(candidates)} candidates "
                f"(score={best_score:.2f})"
            ),
            candidates_evaluated=len(candidates),
            fallback_used=False,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _filter(self, constraints: RoutingConstraints) -> List[ModelProfile]:
        """Keep models meeting quality, latency, and cost constraints.

        Args:
            constraints: The routing constraints.

        Returns:
            Filtered list of model profiles.
        """
        candidates = self._registry.filter(
            min_quality=constraints.quality_threshold,
            max_latency_ms=constraints.latency_budget_ms,
        )

        if constraints.cost_budget is not None:
            candidates = [
                m
                for m in candidates
                if self._avg_cost(m) <= constraints.cost_budget
            ]

        return candidates

    def _score(
        self, candidates: List[ModelProfile]
    ) -> List[Tuple[ModelProfile, float]]:
        """Compute quality/cost ratio for each candidate.

        Args:
            candidates: Models that passed the filter step.

        Returns:
            List of (model, score) tuples.
        """
        scored: List[Tuple[ModelProfile, float]] = []
        for model in candidates:
            avg_cost = self._avg_cost(model)
            if avg_cost <= 0:
                score = model.quality_score * 1000.0  # free model gets top score
            else:
                score = model.quality_score / avg_cost
            scored.append((model, score))
        return scored

    def _select(
        self, scored: List[Tuple[ModelProfile, float]]
    ) -> Tuple[ModelProfile, float]:
        """Pick the candidate with the highest score.

        Args:
            scored: List of (model, score) tuples.

        Returns:
            The best (model, score) tuple.
        """
        return max(scored, key=lambda x: x[1])

    @staticmethod
    def _avg_cost(model: ModelProfile) -> float:
        """Return the average of input and output cost per 1k tokens.

        Args:
            model: Model profile.

        Returns:
            Average cost per 1k tokens.
        """
        return (
            model.cost_per_1k_input_tokens + model.cost_per_1k_output_tokens
        ) / 2

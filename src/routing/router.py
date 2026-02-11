"""
Routing engine for Asahi inference optimizer.

Contains the base Router (filter-score-select) and the AdvancedRouter
(3 modes: AUTOPILOT, GUIDED, EXPLICIT).
"""

import logging
from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel, Field

from src.exceptions import ModelNotFoundError, NoModelsAvailableError
from src.models.registry import (
    ModelProfile,
    ModelRegistry,
    calculate_cost,
    estimate_tokens,
)
from src.routing.constraints import (
    ConstraintInterpreter,
    RoutingConstraints,
    RoutingDecision,
)
from src.routing.task_detector import TaskTypeDetector

logger = logging.getLogger(__name__)

RoutingMode = Literal["autopilot", "guided", "explicit"]


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
        """Keep models meeting quality, latency, and cost constraints."""
        candidates = self._registry.filter(
            min_quality=constraints.quality_threshold,
            max_latency_ms=constraints.latency_budget_ms,
        )
        if constraints.cost_budget is not None:
            candidates = [
                m for m in candidates
                if self._avg_cost(m) <= constraints.cost_budget
            ]
        return candidates

    def _score(
        self, candidates: List[ModelProfile]
    ) -> List[Tuple[ModelProfile, float]]:
        """Compute quality/cost ratio for each candidate."""
        scored: List[Tuple[ModelProfile, float]] = []
        for model in candidates:
            avg_cost = self._avg_cost(model)
            if avg_cost <= 0:
                score = model.quality_score * 1000.0
            else:
                score = model.quality_score / avg_cost
            scored.append((model, score))
        return scored

    def _select(
        self, scored: List[Tuple[ModelProfile, float]]
    ) -> Tuple[ModelProfile, float]:
        """Pick the candidate with the highest score."""
        return max(scored, key=lambda x: x[1])

    @staticmethod
    def _avg_cost(model: ModelProfile) -> float:
        """Return the average of input and output cost per 1k tokens."""
        return (
            model.cost_per_1k_input_tokens + model.cost_per_1k_output_tokens
        ) / 2


# ---------------------------------------------------------------------------
# Advanced Router (3 modes)
# ---------------------------------------------------------------------------


class ModelAlternative(BaseModel):
    """An alternative model suggestion for EXPLICIT mode.

    Attributes:
        model: Model name.
        estimated_cost: Estimated dollar cost for the query.
        estimated_quality: Quality score of the model.
        savings_percent: Percentage savings compared to the chosen model.
    """

    model: str
    estimated_cost: float
    estimated_quality: float
    savings_percent: float


class AdvancedRoutingDecision(BaseModel):
    """Result of an advanced routing decision.

    Attributes:
        model_name: The selected model.
        mode: Which routing mode was used.
        score: Computed quality/cost score.
        reason: Human-readable explanation.
        alternatives: Alternative model suggestions (EXPLICIT mode).
        task_type_detected: Auto-detected task type (if applicable).
    """

    model_name: str
    mode: RoutingMode = "autopilot"
    score: float = 0.0
    reason: str = ""
    alternatives: List[ModelAlternative] = Field(default_factory=list)
    task_type_detected: Optional[str] = None


# Default constraints per task type (for AUTOPILOT mode)
AUTOPILOT_DEFAULTS = {
    "faq": RoutingConstraints(quality_threshold=3.5, latency_budget_ms=300),
    "summarization": RoutingConstraints(quality_threshold=3.5, latency_budget_ms=500),
    "reasoning": RoutingConstraints(quality_threshold=4.0, latency_budget_ms=500),
    "coding": RoutingConstraints(quality_threshold=4.0, latency_budget_ms=500),
    "translation": RoutingConstraints(quality_threshold=3.5, latency_budget_ms=300),
    "classification": RoutingConstraints(quality_threshold=3.0, latency_budget_ms=200),
    "creative": RoutingConstraints(quality_threshold=3.5, latency_budget_ms=500),
    "legal": RoutingConstraints(quality_threshold=4.2, latency_budget_ms=2000),
    "general": RoutingConstraints(quality_threshold=3.5, latency_budget_ms=300),
}


class AdvancedRouter:
    """Three-mode routing engine.

    Modes:
    - **AUTOPILOT**: Auto-detect task type, apply default constraints.
    - **GUIDED**: User provides quality/latency preferences, merged
      with task-type constraints.
    - **EXPLICIT**: User selects a model; Asahi shows alternatives.

    Args:
        registry: The model registry.
        base_router: Phase 1 filter-score-select router.
        task_detector: Task type detector.
        constraint_interpreter: Preference-to-constraint converter.
    """

    def __init__(
        self,
        registry: ModelRegistry,
        base_router: Router,
        task_detector: TaskTypeDetector,
        constraint_interpreter: ConstraintInterpreter,
    ) -> None:
        self._registry = registry
        self._base_router = base_router
        self._detector = task_detector
        self._interpreter = constraint_interpreter

    def route(
        self,
        prompt: str,
        mode: RoutingMode = "autopilot",
        quality_preference: Optional[str] = None,
        latency_preference: Optional[str] = None,
        model_override: Optional[str] = None,
    ) -> AdvancedRoutingDecision:
        """Route a request using the specified mode.

        Args:
            prompt: The user query.
            mode: Routing mode to use.
            quality_preference: User quality preference (GUIDED mode).
            latency_preference: User latency preference (GUIDED mode).
            model_override: User-selected model (EXPLICIT mode).

        Returns:
            AdvancedRoutingDecision with the selected model and metadata.

        Raises:
            ModelNotFoundError: In EXPLICIT mode if model_override is unknown.
            ValueError: In GUIDED mode if preferences are invalid.
        """
        if mode == "autopilot":
            return self._route_autopilot(prompt)
        elif mode == "guided":
            return self._route_guided(
                prompt, quality_preference, latency_preference
            )
        elif mode == "explicit":
            return self._route_explicit(prompt, model_override)
        else:
            raise ValueError(f"Unknown routing mode: {mode}")

    def _route_autopilot(self, prompt: str) -> AdvancedRoutingDecision:
        """AUTOPILOT: auto-detect task type, apply defaults."""
        detection = self._detector.detect(prompt)
        task_type = detection.task_type

        if detection.confidence < 0.3:
            logger.warning(
                "Low confidence task detection; using general",
                extra={
                    "detected": task_type,
                    "confidence": detection.confidence,
                },
            )
            task_type = "general"

        constraints = AUTOPILOT_DEFAULTS.get(
            task_type, AUTOPILOT_DEFAULTS["general"],
        )
        decision = self._base_router.select_model(constraints)

        return AdvancedRoutingDecision(
            model_name=decision.model_name,
            mode="autopilot",
            score=decision.score,
            reason=(
                f"Auto-detected '{task_type}' "
                f"(confidence={detection.confidence:.0%}): "
                f"{decision.reason}"
            ),
            task_type_detected=task_type,
        )

    def _route_guided(
        self,
        prompt: str,
        quality_preference: Optional[str],
        latency_preference: Optional[str],
    ) -> AdvancedRoutingDecision:
        """GUIDED: merge user preferences with task-type constraints."""
        detection = self._detector.detect(prompt)
        task_type = detection.task_type

        constraints = self._interpreter.interpret(
            quality_preference=quality_preference,
            latency_preference=latency_preference,
            task_type=task_type,
        )
        decision = self._base_router.select_model(constraints)

        return AdvancedRoutingDecision(
            model_name=decision.model_name,
            mode="guided",
            score=decision.score,
            reason=(
                f"User preference (quality={quality_preference}, "
                f"latency={latency_preference}) + "
                f"task '{task_type}': {decision.reason}"
            ),
            task_type_detected=task_type,
        )

    def _route_explicit(
        self,
        prompt: str,
        model_override: Optional[str],
    ) -> AdvancedRoutingDecision:
        """EXPLICIT: use specified model, show alternatives."""
        if not model_override:
            raise ValueError("model_override is required for EXPLICIT mode")

        chosen_profile = self._registry.get(model_override)

        input_tokens = estimate_tokens(prompt)
        output_tokens = max(20, int(input_tokens * 0.6))
        chosen_cost = calculate_cost(
            chosen_profile, input_tokens, output_tokens
        )

        alternatives: List[ModelAlternative] = []
        for profile in self._registry.all():
            if profile.name == model_override:
                continue
            alt_cost = calculate_cost(profile, input_tokens, output_tokens)
            savings_pct = (
                ((chosen_cost - alt_cost) / chosen_cost * 100)
                if chosen_cost > 0
                else 0.0
            )
            alternatives.append(
                ModelAlternative(
                    model=profile.name,
                    estimated_cost=round(alt_cost, 6),
                    estimated_quality=profile.quality_score,
                    savings_percent=round(savings_pct, 1),
                )
            )
        alternatives.sort(key=lambda a: a.savings_percent, reverse=True)

        return AdvancedRoutingDecision(
            model_name=model_override,
            mode="explicit",
            score=chosen_profile.quality_score,
            reason=(
                f"User selected {model_override}; "
                f"{len(alternatives)} alternatives available"
            ),
            alternatives=alternatives,
            task_type_detected=None,
        )

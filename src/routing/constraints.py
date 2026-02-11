"""
Routing constraints and constraint interpreter for Asahi.

Contains RoutingConstraints, RoutingDecision (data models used by
the router), and ConstraintInterpreter (converts human-friendly
preferences into numeric constraints).
"""

import logging
from typing import Dict, Optional

from pydantic import BaseModel, Field

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


# Quality preference -> quality threshold mapping
QUALITY_MAP: Dict[str, float] = {
    "low": 3.0,
    "medium": 3.5,
    "high": 4.0,
    "max": 4.5,
}

# Latency preference -> latency budget (ms) mapping
LATENCY_MAP: Dict[str, int] = {
    "slow": 2000,
    "normal": 500,
    "fast": 300,
    "instant": 150,
}

# Task-type overrides: task_type -> (min_quality, max_latency)
TASK_OVERRIDES: Dict[str, Dict[str, float]] = {
    "coding": {"min_quality": 4.0, "max_latency": 500},
    "reasoning": {"min_quality": 4.0, "max_latency": 500},
    "legal": {"min_quality": 4.2, "max_latency": 2000},
}


class ConstraintInterpreter:
    """Convert human-friendly preferences into numeric routing constraints.

    Applies task-type overrides after user preferences: quality floors
    are raised (``max``) and latency budgets are tightened (``min``)
    where the task demands it.
    """

    def interpret(
        self,
        quality_preference: Optional[str] = None,
        latency_preference: Optional[str] = None,
        task_type: str = "general",
    ) -> RoutingConstraints:
        """Interpret user preferences into RoutingConstraints.

        Args:
            quality_preference: One of ``"low"``, ``"medium"``, ``"high"``,
                ``"max"``, or ``None`` (defaults to ``"medium"``).
            latency_preference: One of ``"slow"``, ``"normal"``, ``"fast"``,
                ``"instant"``, or ``None`` (defaults to ``"normal"``).
            task_type: Detected task category for override logic.

        Returns:
            RoutingConstraints with the resolved quality threshold
            and latency budget.

        Raises:
            ValueError: If an unrecognised preference value is given.
        """
        # Resolve quality
        quality_pref = quality_preference or "medium"
        if quality_pref not in QUALITY_MAP:
            raise ValueError(
                f"Invalid quality_preference '{quality_pref}'. "
                f"Allowed: {list(QUALITY_MAP.keys())}"
            )
        quality_threshold = QUALITY_MAP[quality_pref]

        # Resolve latency
        latency_pref = latency_preference or "normal"
        if latency_pref not in LATENCY_MAP:
            raise ValueError(
                f"Invalid latency_preference '{latency_pref}'. "
                f"Allowed: {list(LATENCY_MAP.keys())}"
            )
        latency_budget_ms = LATENCY_MAP[latency_pref]

        # Apply task-type overrides
        if task_type in TASK_OVERRIDES:
            overrides = TASK_OVERRIDES[task_type]
            min_quality = overrides.get("min_quality", 0.0)
            max_latency = overrides.get("max_latency", 99999)

            quality_threshold = max(quality_threshold, min_quality)
            latency_budget_ms = min(latency_budget_ms, int(max_latency))

            logger.debug(
                "Task-type override applied",
                extra={
                    "task_type": task_type,
                    "quality_threshold": quality_threshold,
                    "latency_budget_ms": latency_budget_ms,
                },
            )

        return RoutingConstraints(
            quality_threshold=quality_threshold,
            latency_budget_ms=latency_budget_ms,
        )

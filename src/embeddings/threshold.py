"""
Adaptive threshold tuner for Asahi semantic caching.

Selects the optimal similarity threshold per task type and cost
sensitivity level.  Thresholds are configurable and can be updated
at runtime based on observed performance data.
"""

import logging
from typing import Dict, Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

CostSensitivity = Literal["high", "medium", "low"]

# Default thresholds: task_type -> {sensitivity -> threshold}
DEFAULT_THRESHOLDS: Dict[str, Dict[str, float]] = {
    "faq": {"high": 0.70, "medium": 0.80, "low": 0.90},
    "summarization": {"high": 0.80, "medium": 0.85, "low": 0.92},
    "reasoning": {"high": 0.85, "medium": 0.90, "low": 0.95},
    "coding": {"high": 0.90, "medium": 0.93, "low": 0.97},
    "legal": {"high": 0.88, "medium": 0.92, "low": 0.96},
    "default": {"high": 0.80, "medium": 0.85, "low": 0.92},
}


class ThresholdConfig(BaseModel):
    """Configuration for adaptive threshold tuning.

    Attributes:
        thresholds: Nested dict mapping
            ``task_type -> cost_sensitivity -> threshold_value``.
    """

    thresholds: Dict[str, Dict[str, float]] = Field(
        default_factory=lambda: {
            k: dict(v) for k, v in DEFAULT_THRESHOLDS.items()
        }
    )


class AdaptiveThresholdTuner:
    """Select and manage per-task similarity thresholds.

    Higher sensitivity (``"low"``) means stricter thresholds --
    the cache is less likely to return a semantically similar but
    not-exact match.  Lower sensitivity (``"high"``) allows more
    aggressive caching.

    Args:
        config: Threshold configuration.  If ``None``, defaults are used.
    """

    def __init__(self, config: ThresholdConfig | None = None) -> None:
        self._config = config or ThresholdConfig()

    def get_threshold(
        self,
        task_type: str,
        cost_sensitivity: CostSensitivity = "medium",
    ) -> float:
        """Return the similarity threshold for a given task and sensitivity.

        Args:
            task_type: The detected task category (e.g. ``"faq"``).
            cost_sensitivity: How aggressively to cache.
                ``"high"`` = cache aggressively (lower threshold),
                ``"low"`` = cache conservatively (higher threshold).

        Returns:
            Threshold value between 0.0 and 1.0.
        """
        task_thresholds = self._config.thresholds.get(
            task_type,
            self._config.thresholds.get("default", {"medium": 0.85}),
        )
        threshold = task_thresholds.get(
            cost_sensitivity,
            task_thresholds.get("medium", 0.85),
        )
        return threshold

    def update_threshold(
        self,
        task_type: str,
        cost_sensitivity: str,
        new_threshold: float,
    ) -> None:
        """Update a specific threshold at runtime.

        Args:
            task_type: The task category to update.
            cost_sensitivity: The sensitivity level to update.
            new_threshold: New threshold value (0.0 to 1.0).

        Raises:
            ValueError: If new_threshold is outside [0.0, 1.0].
        """
        if not (0.0 <= new_threshold <= 1.0):
            raise ValueError(
                f"Threshold must be in [0.0, 1.0], got {new_threshold}"
            )

        if task_type not in self._config.thresholds:
            self._config.thresholds[task_type] = dict(
                self._config.thresholds.get(
                    "default", {"high": 0.80, "medium": 0.85, "low": 0.92}
                )
            )

        self._config.thresholds[task_type][cost_sensitivity] = new_threshold

        logger.info(
            "Threshold updated",
            extra={
                "task_type": task_type,
                "cost_sensitivity": cost_sensitivity,
                "new_threshold": new_threshold,
            },
        )

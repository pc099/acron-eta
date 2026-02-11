"""
Mismatch cost calculator for Asahi semantic caching.

Determines whether using a cached response (with some semantic distance)
is economically cheaper than recomputing via a fresh LLM call.
This is the economic engine behind Tier 2 cache decisions.
"""

import logging
from typing import Dict, Tuple

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Default task sensitivity weights.
# Lower weight = more aggressive caching; higher = more conservative.
DEFAULT_TASK_WEIGHTS: Dict[str, float] = {
    "faq": 1.0,
    "summarization": 1.5,
    "general": 1.5,
    "translation": 1.5,
    "classification": 1.0,
    "creative": 2.0,
    "reasoning": 2.5,
    "coding": 3.0,
    "legal": 4.0,
}


class MismatchConfig(BaseModel):
    """Configuration for mismatch cost calculation.

    Attributes:
        quality_penalty_weight: Global multiplier for quality risk.
        task_weights: Per-task sensitivity weights.  Higher values
            make the calculator more conservative (less likely to
            reuse cached responses).
    """

    quality_penalty_weight: float = Field(default=2.0, ge=0.0)
    task_weights: Dict[str, float] = Field(
        default_factory=lambda: dict(DEFAULT_TASK_WEIGHTS)
    )


class MismatchCostCalculator:
    """Evaluate the economic cost of using a semantically similar cached response.

    The core formula is::

        mismatch_cost = (1 - similarity) * quality_penalty_weight
                        * task_weight * model_cost

    If the mismatch cost is lower than the recompute cost, the cache
    entry should be used.

    Args:
        config: Mismatch cost configuration.
    """

    def __init__(self, config: MismatchConfig | None = None) -> None:
        self._config = config or MismatchConfig()

    def calculate_mismatch_cost(
        self,
        similarity: float,
        task_type: str,
        model_cost: float,
    ) -> float:
        """Calculate the quality-risk cost of using a cached response.

        Args:
            similarity: Cosine similarity between query and cached entry
                (0.0 to 1.0).
            task_type: The detected task category.
            model_cost: Dollar cost of a fresh inference call.

        Returns:
            Dollar cost of the mismatch risk.
        """
        task_weight = self._config.task_weights.get(
            task_type,
            self._config.task_weights.get("general", 1.5),
        )
        mismatch = (
            (1.0 - similarity)
            * self._config.quality_penalty_weight
            * task_weight
            * model_cost
        )
        return round(mismatch, 8)

    def should_use_cache(
        self,
        similarity: float,
        task_type: str,
        recompute_cost: float,
    ) -> Tuple[bool, str]:
        """Decide whether to use a cached response or recompute.

        Args:
            similarity: Cosine similarity between query and cached entry.
            task_type: The detected task category.
            recompute_cost: Dollar cost of a fresh inference call.

        Returns:
            Tuple of (should_cache, reason_string).
        """
        mc = self.calculate_mismatch_cost(similarity, task_type, recompute_cost)

        if mc < recompute_cost:
            reason = (
                f"Using cache: mismatch cost ${mc:.6f} < "
                f"recompute cost ${recompute_cost:.6f} "
                f"(similarity={similarity:.3f}, task={task_type})"
            )
            logger.debug(reason)
            return True, reason
        else:
            reason = (
                f"Recomputing: mismatch cost ${mc:.6f} >= "
                f"recompute cost ${recompute_cost:.6f} "
                f"(similarity={similarity:.3f}, task={task_type})"
            )
            logger.debug(reason)
            return False, reason

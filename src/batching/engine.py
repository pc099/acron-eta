"""
Batch eligibility engine for Asahi inference optimizer.

Decides whether a request is eligible for batching and determines
which batch group it belongs to.  Eligibility is based on latency
budget, task type, and prompt token count relative to model capacity.
"""

import logging
from typing import List, Optional

from pydantic import BaseModel, Field

from src.config import get_settings
from src.exceptions import BatchingError
from src.models.registry import ModelRegistry, estimate_tokens

logger = logging.getLogger(__name__)


class BatchConfig(BaseModel):
    """Configuration for the batch engine.

    Attributes:
        min_batch_size: Minimum requests to form a batch.
        max_batch_size: Maximum requests per batch.
        max_wait_ms: Global max wait before flushing a batch (ms).
        latency_threshold_ms: Requests with budget below this skip batching.
        eligible_task_types: Only these task types can be batched.
    """

    min_batch_size: int = Field(default=2, ge=1)
    max_batch_size: int = Field(default=10, ge=1)
    max_wait_ms: int = Field(default=500, ge=0)
    latency_threshold_ms: int = Field(default=200, ge=0)
    eligible_task_types: List[str] = Field(
        default=["summarization", "faq", "translation"]
    )


class BatchEligibility(BaseModel):
    """Result of batch eligibility evaluation.

    Attributes:
        eligible: Whether the request can be batched.
        reason: Human-readable explanation for the decision.
        batch_group: Batch group key, e.g. ``"summarization:sonnet"``.
            ``None`` when ineligible.
        max_wait_ms: How long this request can wait for a batch to form.
    """

    eligible: bool
    reason: str
    batch_group: Optional[str] = None
    max_wait_ms: int = 0


class BatchEngine:
    """Evaluate whether incoming requests are eligible for batching.

    Uses task type, latency budget, and prompt token count to decide
    whether a request can be grouped with others into a single API call.

    Args:
        config: Batch configuration parameters.
        model_registry: Registry used to look up model capacity.
    """

    def __init__(
        self,
        config: Optional[BatchConfig] = None,
        model_registry: Optional[ModelRegistry] = None,
    ) -> None:
        if config is None:
            _s = get_settings().batching
            config = BatchConfig(
                min_batch_size=_s.min_batch_size,
                max_batch_size=_s.max_batch_size,
                max_wait_ms=_s.max_wait_ms,
                latency_threshold_ms=_s.latency_threshold_ms,
                eligible_task_types=_s.eligible_task_types,
            )
        self._config = config
        self._registry = model_registry

        logger.info(
            "BatchEngine initialised",
            extra={
                "max_batch_size": self._config.max_batch_size,
                "max_wait_ms": self._config.max_wait_ms,
                "eligible_tasks": self._config.eligible_task_types,
            },
        )

    def evaluate(
        self,
        prompt: str,
        task_type: str,
        model: str,
        latency_budget_ms: int,
    ) -> BatchEligibility:
        """Evaluate whether a request is eligible for batching.

        Args:
            prompt: The user's input prompt text.
            task_type: Detected or declared task type (e.g. ``"summarization"``).
            model: Target model name (e.g. ``"claude-3-5-sonnet"``).
            latency_budget_ms: Maximum acceptable end-to-end latency in ms.

        Returns:
            BatchEligibility with eligibility decision, reason, group key,
            and maximum wait time.

        Raises:
            BatchingError: If evaluation fails due to an unexpected error.
        """
        try:
            return self._evaluate_internal(
                prompt, task_type, model, latency_budget_ms
            )
        except BatchingError:
            raise
        except Exception as exc:
            logger.error(
                "Batch eligibility evaluation failed",
                extra={"model": model, "task_type": task_type, "error": str(exc)},
                exc_info=True,
            )
            raise BatchingError(
                f"Failed to evaluate batch eligibility: {exc}"
            ) from exc

    def _evaluate_internal(
        self,
        prompt: str,
        task_type: str,
        model: str,
        latency_budget_ms: int,
    ) -> BatchEligibility:
        """Core eligibility logic without top-level error wrapping.

        Args:
            prompt: The user's input prompt text.
            task_type: Detected or declared task type.
            model: Target model name.
            latency_budget_ms: Maximum acceptable latency in ms.

        Returns:
            BatchEligibility result.
        """
        # Rule 1: latency budget too tight
        if latency_budget_ms < self._config.latency_threshold_ms:
            logger.debug(
                "Request ineligible: latency budget too tight",
                extra={
                    "latency_budget_ms": latency_budget_ms,
                    "threshold_ms": self._config.latency_threshold_ms,
                },
            )
            return BatchEligibility(
                eligible=False,
                reason=(
                    f"Latency budget {latency_budget_ms}ms is below "
                    f"threshold {self._config.latency_threshold_ms}ms"
                ),
            )

        # Rule 2: task type not eligible
        if task_type not in self._config.eligible_task_types:
            logger.debug(
                "Request ineligible: task type not batchable",
                extra={
                    "task_type": task_type,
                    "eligible_types": self._config.eligible_task_types,
                },
            )
            return BatchEligibility(
                eligible=False,
                reason=(
                    f"Task type '{task_type}' is not eligible for batching. "
                    f"Eligible types: {self._config.eligible_task_types}"
                ),
            )

        # Rule 3: prompt too large relative to model capacity
        token_count = estimate_tokens(prompt)
        max_tokens_per_request = self._get_max_input_tokens(model)

        if max_tokens_per_request is not None:
            per_request_limit = max_tokens_per_request // self._config.max_batch_size
            if token_count > per_request_limit:
                logger.debug(
                    "Request ineligible: prompt too large for batching",
                    extra={
                        "token_count": token_count,
                        "per_request_limit": per_request_limit,
                        "model": model,
                    },
                )
                return BatchEligibility(
                    eligible=False,
                    reason=(
                        f"Prompt token count ({token_count}) exceeds "
                        f"per-request batch limit ({per_request_limit}) "
                        f"for model '{model}'"
                    ),
                )

        # Eligible: compute batch group and max wait
        batch_group = f"{task_type}:{model}"
        estimated_inference_ms = self._estimate_inference_ms(model)
        max_wait_ms = min(
            max(0, latency_budget_ms - estimated_inference_ms),
            self._config.max_wait_ms,
        )

        logger.info(
            "Request eligible for batching",
            extra={
                "batch_group": batch_group,
                "max_wait_ms": max_wait_ms,
                "token_count": token_count,
            },
        )

        return BatchEligibility(
            eligible=True,
            reason="Request is eligible for batching",
            batch_group=batch_group,
            max_wait_ms=max_wait_ms,
        )

    def _get_max_input_tokens(self, model: str) -> Optional[int]:
        """Look up model's max input token capacity.

        Args:
            model: Model name to look up.

        Returns:
            Max input tokens, or ``None`` if registry is unavailable.
        """
        if self._registry is None:
            return None
        try:
            profile = self._registry.get(model)
            return profile.max_input_tokens
        except Exception:
            logger.warning(
                "Could not look up model capacity; skipping token check",
                extra={"model": model},
            )
            return None

    def _estimate_inference_ms(self, model: str) -> int:
        """Estimate inference latency for a model.

        Args:
            model: Model name to look up.

        Returns:
            Estimated latency in ms, or a conservative default.
        """
        if self._registry is None:
            return 100  # conservative default
        try:
            profile = self._registry.get(model)
            return profile.avg_latency_ms
        except Exception:
            return 100

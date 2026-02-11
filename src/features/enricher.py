"""
Feature enricher for Asahi inference optimizer.

Takes an incoming LLM request and enriches it with relevant features
from the feature store.  Features are formatted into a context block
prepended to the prompt, enabling cheaper models to produce outputs
comparable to expensive ones.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from src.features.client import FeatureStoreClient, FeatureVector
from src.models.registry import estimate_tokens

logger = logging.getLogger(__name__)


class EnricherConfig(BaseModel):
    """Configuration for the FeatureEnricher.

    Attributes:
        max_feature_tokens: Maximum tokens to add from features.
        freshness_threshold_seconds: Reject features older than this.
        enabled_task_types: Tasks that benefit from enrichment.
        context_header: Header text for the enrichment block.
        context_footer: Footer text for the enrichment block.
    """

    max_feature_tokens: int = Field(default=200, ge=0)
    freshness_threshold_seconds: int = Field(default=3600, ge=0)
    enabled_task_types: List[str] = Field(
        default=["general", "summarization", "faq",
                 "recommendation", "support", "coding"]
    )
    context_header: str = "[Context from user profile]"
    context_footer: str = "[End context]"


class EnrichmentResult(BaseModel):
    """Result of a feature enrichment operation.

    Attributes:
        original_prompt: The prompt before enrichment.
        enriched_prompt: The prompt with feature context prepended.
        features_used: Names of features that were included.
        feature_tokens_added: Number of tokens added by enrichment.
        enrichment_latency_ms: Time taken for the enrichment in ms.
        features_available: Whether the feature store returned data.
    """

    original_prompt: str
    enriched_prompt: str
    features_used: List[str] = Field(default_factory=list)
    feature_tokens_added: int = 0
    enrichment_latency_ms: float = 0.0
    features_available: bool = False


# Task-to-feature mapping: which features are useful for each task type
TASK_FEATURE_MAP: Dict[str, Dict[str, List[str]]] = {
    "recommendation": {
        "user": ["purchase_history", "browsing_history", "preferences",
                 "preference_score", "demographics"],
        "product": ["category", "price_range", "popularity"],
    },
    "support": {
        "user": ["tier", "recent_tickets", "products_owned",
                 "satisfaction_score"],
        "organization": ["plan", "account_status"],
    },
    "coding": {
        "user": ["language_preferences", "framework_history",
                 "recent_projects", "skill_level"],
    },
    "summarization": {
        "user": ["reading_level", "preferred_length", "domain_expertise"],
        "organization": ["brand_voice", "tone", "style_guide"],
    },
    "faq": {
        "user": ["recent_queries", "domain_expertise", "tier"],
    },
    "general": {
        "user": ["preferences", "domain_expertise", "tier"],
        "organization": ["brand_voice", "industry"],
    },
}


class FeatureEnricher:
    """Enrich LLM prompts with features from a feature store.

    Fetches relevant features for the user/organization, formats them
    into a context block, and prepends it to the prompt.  Respects
    token limits, freshness thresholds, and task-type relevance.

    Args:
        client: A feature store backend implementing
            :class:`FeatureStoreClient`.
        config: Enricher configuration.
    """

    def __init__(
        self,
        client: FeatureStoreClient,
        config: Optional[EnricherConfig] = None,
    ) -> None:
        self._client = client
        self._config = config or EnricherConfig()

        logger.info(
            "FeatureEnricher initialised",
            extra={
                "max_tokens": self._config.max_feature_tokens,
                "freshness_threshold": self._config.freshness_threshold_seconds,
            },
        )

    def enrich(
        self,
        prompt: str,
        user_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        task_type: str = "general",
        context: Optional[Dict[str, Any]] = None,
    ) -> EnrichmentResult:
        """Enrich a prompt with feature store data.

        Args:
            prompt: The original user prompt.
            user_id: Optional user entity ID for feature lookup.
            organization_id: Optional organization entity ID.
            task_type: Detected or declared task type.
            context: Optional extra context dict (passed through).

        Returns:
            :class:`EnrichmentResult` with the enriched prompt and
            metadata.
        """
        start_time = time.perf_counter()

        # If task type is not in the enabled list, skip enrichment
        if task_type not in self._config.enabled_task_types:
            elapsed = (time.perf_counter() - start_time) * 1000
            logger.debug(
                "Enrichment skipped: task type not enabled",
                extra={"task_type": task_type},
            )
            return EnrichmentResult(
                original_prompt=prompt,
                enriched_prompt=prompt,
                enrichment_latency_ms=round(elapsed, 2),
                features_available=False,
            )

        # If no entity IDs, nothing to enrich
        if not user_id and not organization_id:
            elapsed = (time.perf_counter() - start_time) * 1000
            return EnrichmentResult(
                original_prompt=prompt,
                enriched_prompt=prompt,
                enrichment_latency_ms=round(elapsed, 2),
                features_available=False,
            )

        # Fetch features
        all_features: Dict[str, Any] = {}
        features_used: List[str] = []

        if user_id:
            user_feature_names = self.get_relevant_features(task_type, "user")
            if user_feature_names:
                user_vec = self._safe_get_features(
                    user_id, "user", user_feature_names
                )
                if user_vec and self._is_fresh(user_vec):
                    all_features.update(user_vec.features)
                    features_used.extend(list(user_vec.features.keys()))

        if organization_id:
            org_feature_names = self.get_relevant_features(
                task_type, "organization"
            )
            if org_feature_names:
                org_vec = self._safe_get_features(
                    organization_id, "organization", org_feature_names
                )
                if org_vec and self._is_fresh(org_vec):
                    all_features.update(org_vec.features)
                    features_used.extend(list(org_vec.features.keys()))

        # Format context block
        if all_features:
            context_block = self._format_context(all_features)
            # Check token budget
            context_tokens = estimate_tokens(context_block)
            if context_tokens > self._config.max_feature_tokens:
                context_block = self._trim_context(
                    all_features, self._config.max_feature_tokens
                )
                context_tokens = estimate_tokens(context_block)
                # Recalculate features_used based on what was kept
                features_used = self._features_in_block(
                    context_block, features_used
                )

            enriched_prompt = f"{context_block}\n\n{prompt}"
        else:
            enriched_prompt = prompt
            context_tokens = 0

        elapsed = (time.perf_counter() - start_time) * 1000

        logger.info(
            "Enrichment complete",
            extra={
                "features_used": len(features_used),
                "tokens_added": context_tokens,
                "latency_ms": round(elapsed, 2),
                "task_type": task_type,
            },
        )

        return EnrichmentResult(
            original_prompt=prompt,
            enriched_prompt=enriched_prompt,
            features_used=features_used,
            feature_tokens_added=context_tokens,
            enrichment_latency_ms=round(elapsed, 2),
            features_available=bool(all_features),
        )

    def get_relevant_features(
        self,
        task_type: str,
        entity_type: str,
    ) -> List[str]:
        """Determine which features are relevant for a task and entity.

        Args:
            task_type: The task type (e.g. ``"recommendation"``).
            entity_type: Entity category (e.g. ``"user"``).

        Returns:
            List of feature names to request from the store.
        """
        task_map = TASK_FEATURE_MAP.get(task_type, TASK_FEATURE_MAP.get("general", {}))
        return list(task_map.get(entity_type, []))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _safe_get_features(
        self,
        entity_id: str,
        entity_type: str,
        feature_names: List[str],
    ) -> Optional[FeatureVector]:
        """Fetch features with error handling.

        Args:
            entity_id: Entity identifier.
            entity_type: Entity category.
            feature_names: Features to request.

        Returns:
            :class:`FeatureVector` or ``None`` on failure.
        """
        try:
            return self._client.get_features(
                entity_id, entity_type, feature_names
            )
        except Exception as exc:
            logger.warning(
                "Feature fetch failed; proceeding without enrichment",
                extra={
                    "entity_id": entity_id,
                    "entity_type": entity_type,
                    "error": str(exc),
                },
            )
            return None

    def _is_fresh(self, vector: FeatureVector) -> bool:
        """Check whether a feature vector is fresh enough.

        A threshold of ``0`` means only accept data with zero age
        (effectively rejects all real-world data).  Set a high value
        (e.g. ``999999``) to disable the freshness check entirely.

        Args:
            vector: The retrieved feature vector.

        Returns:
            ``True`` if freshness is within threshold.
        """
        return vector.freshness_seconds <= self._config.freshness_threshold_seconds

    def _format_context(self, features: Dict[str, Any]) -> str:
        """Format features into a context block.

        Args:
            features: Feature name-value mapping.

        Returns:
            Formatted context string.
        """
        lines = [self._config.context_header]
        for key, value in features.items():
            formatted = self._format_value(key, value)
            lines.append(f"- {formatted}")
        lines.append(self._config.context_footer)
        return "\n".join(lines)

    def _trim_context(
        self,
        features: Dict[str, Any],
        max_tokens: int,
    ) -> str:
        """Build a context block that fits within the token budget.

        Greedily adds features until the budget is exhausted.

        Args:
            features: All available features.
            max_tokens: Maximum token count.

        Returns:
            Trimmed context string.
        """
        lines = [self._config.context_header]
        footer = self._config.context_footer
        current_tokens = estimate_tokens(
            self._config.context_header + "\n" + footer
        )

        for key, value in features.items():
            line = f"- {self._format_value(key, value)}"
            line_tokens = estimate_tokens(line)
            if current_tokens + line_tokens <= max_tokens:
                lines.append(line)
                current_tokens += line_tokens
            else:
                break

        lines.append(footer)
        return "\n".join(lines)

    @staticmethod
    def _format_value(key: str, value: Any) -> str:
        """Format a single feature key-value pair.

        Args:
            key: Feature name.
            value: Feature value.

        Returns:
            Human-readable string.
        """
        display_key = key.replace("_", " ").title()
        if isinstance(value, list):
            return f"{display_key}: {', '.join(str(v) for v in value)}"
        return f"{display_key}: {value}"

    @staticmethod
    def _features_in_block(
        block: str,
        original_features: List[str],
    ) -> List[str]:
        """Determine which features made it into a trimmed block.

        Args:
            block: The formatted context block.
            original_features: All candidate feature names.

        Returns:
            List of feature names present in the block.
        """
        present: List[str] = []
        for name in original_features:
            display = name.replace("_", " ").title()
            if display in block:
                present.append(name)
        return present

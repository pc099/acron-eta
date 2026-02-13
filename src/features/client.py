"""
Feature store client abstraction for Asahi inference optimizer.

Provides a unified ``FeatureStoreClient`` Protocol for retrieving
entity features from any backend (Feast, Tecton, custom HTTP, or
local JSON).  The :class:`LocalFeatureStore` implementation is always
available for development and testing.
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from src.config import get_settings
from src.exceptions import FeatureConfigError, FeatureStoreError

logger = logging.getLogger(__name__)


class FeatureStoreConfig(BaseModel):
    """Configuration for feature store connectivity.

    Attributes:
        provider: Which feature store backend to use.
        timeout_ms: Maximum wait for a feature fetch (ms).
        fallback_on_timeout: If ``True``, proceed without features
            when the store is slow rather than raising.
        local_data_path: Path to a JSON file for the local store.
        feast_repo_path: Path to the Feast repository.
        feast_project: Feast project name.
        tecton_api_key_env: Env var holding the Tecton API key.
        tecton_workspace: Tecton workspace identifier.
    """

    provider: Literal["feast", "tecton", "custom", "local"] = "local"
    timeout_ms: int = Field(default=200, ge=0)
    fallback_on_timeout: bool = True
    local_data_path: str = Field(default_factory=lambda: get_settings().feature_store.local_data_path)
    feast_repo_path: str = ""
    feast_project: str = "asahi"
    tecton_api_key_env: str = "TECTON_API_KEY"
    tecton_workspace: str = "production"


class FeatureVector(BaseModel):
    """A set of features retrieved for a single entity.

    Attributes:
        entity_id: Unique identifier for the entity.
        entity_type: Category such as ``"user"``, ``"product"``,
            ``"organization"``.
        features: Mapping of feature name to value.
        retrieved_at: UTC timestamp of retrieval.
        freshness_seconds: Age of the underlying data in seconds.
        source: Which backend provided the data.
    """

    entity_id: str
    entity_type: str
    features: Dict[str, Any] = Field(default_factory=dict)
    retrieved_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    freshness_seconds: float = 0.0
    source: str = "local"


@runtime_checkable
class FeatureStoreClient(Protocol):
    """Protocol for feature store backends.

    Any concrete implementation must provide these three methods.
    """

    def get_features(
        self,
        entity_id: str,
        entity_type: str,
        feature_names: List[str],
    ) -> FeatureVector:
        """Retrieve features for a single entity.

        Args:
            entity_id: Entity identifier.
            entity_type: Entity category.
            feature_names: Which features to fetch.

        Returns:
            Populated :class:`FeatureVector`.
        """
        ...

    def get_batch_features(
        self,
        entity_ids: List[str],
        entity_type: str,
        feature_names: List[str],
    ) -> List[FeatureVector]:
        """Retrieve features for multiple entities.

        Args:
            entity_ids: List of entity identifiers.
            entity_type: Shared entity category.
            feature_names: Which features to fetch.

        Returns:
            List of :class:`FeatureVector` objects (same order as IDs).
        """
        ...

    def health_check(self) -> bool:
        """Check whether the feature store is reachable.

        Returns:
            ``True`` if healthy, ``False`` otherwise.
        """
        ...


# ------------------------------------------------------------------
# Local (JSON file) implementation
# ------------------------------------------------------------------


class LocalFeatureStore:
    """JSON-file backed feature store for development and testing.

    The JSON file should have the structure::

        {
            "user": {
                "user-123": {
                    "purchase_history": ["shoes", "jacket"],
                    "preference_score": 0.8,
                    "_updated_at": "2026-02-10T12:00:00Z"
                }
            },
            "product": { ... }
        }

    Args:
        data_path: Path to the JSON data file.
    """

    def __init__(self, data_path: Optional[Path] = None) -> None:
        self._data: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._path = data_path

        if data_path is not None and data_path.exists():
            self._load(data_path)

        logger.info(
            "LocalFeatureStore initialised",
            extra={"data_path": str(data_path), "entities": self._entity_count()},
        )

    def get_features(
        self,
        entity_id: str,
        entity_type: str,
        feature_names: List[str],
    ) -> FeatureVector:
        """Retrieve features for one entity from local JSON data.

        Args:
            entity_id: Entity identifier.
            entity_type: Entity category.
            feature_names: Which features to return.

        Returns:
            :class:`FeatureVector` with requested features (empty if
            entity or features are not found).

        Raises:
            FeatureConfigError: If a requested feature name is not in
                the data and strict mode is desired (currently logs only).
        """
        now = datetime.now(timezone.utc)
        type_data = self._data.get(entity_type, {})
        entity_data = type_data.get(entity_id, {})

        if not entity_data:
            logger.info(
                "Entity not found in local store",
                extra={"entity_id": entity_id, "entity_type": entity_type},
            )
            return FeatureVector(
                entity_id=entity_id,
                entity_type=entity_type,
                features={},
                retrieved_at=now,
                freshness_seconds=0.0,
                source="local",
            )

        # Calculate freshness
        updated_at_str = entity_data.get("_updated_at", "")
        freshness = self._calculate_freshness(updated_at_str, now)

        # Pick requested features
        features: Dict[str, Any] = {}
        available_keys = {
            k for k in entity_data.keys() if not k.startswith("_")
        }
        for name in feature_names:
            if name in entity_data:
                features[name] = entity_data[name]
            else:
                logger.debug(
                    "Feature not found for entity",
                    extra={
                        "feature": name,
                        "entity_id": entity_id,
                        "available": list(available_keys),
                    },
                )

        return FeatureVector(
            entity_id=entity_id,
            entity_type=entity_type,
            features=features,
            retrieved_at=now,
            freshness_seconds=freshness,
            source="local",
        )

    def get_batch_features(
        self,
        entity_ids: List[str],
        entity_type: str,
        feature_names: List[str],
    ) -> List[FeatureVector]:
        """Retrieve features for multiple entities.

        Args:
            entity_ids: List of entity identifiers.
            entity_type: Shared entity category.
            feature_names: Which features to fetch.

        Returns:
            List of :class:`FeatureVector` objects.
        """
        return [
            self.get_features(eid, entity_type, feature_names)
            for eid in entity_ids
        ]

    def health_check(self) -> bool:
        """Check store health.

        Returns:
            ``True`` -- local store is always available.
        """
        return True

    def add_entity(
        self,
        entity_type: str,
        entity_id: str,
        features: Dict[str, Any],
    ) -> None:
        """Add or update an entity in the local store.

        This is a convenience method for testing and development.

        Args:
            entity_type: Entity category.
            entity_id: Entity identifier.
            features: Feature data to store.
        """
        if entity_type not in self._data:
            self._data[entity_type] = {}
        self._data[entity_type][entity_id] = {
            **features,
            "_updated_at": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load(self, path: Path) -> None:
        """Load data from a JSON file.

        Args:
            path: Path to JSON file.

        Raises:
            FeatureStoreError: If the file cannot be parsed.
        """
        try:
            with open(path, "r", encoding="utf-8") as fh:
                self._data = json.load(fh)
            logger.info("Local features loaded", extra={"path": str(path)})
        except json.JSONDecodeError as exc:
            raise FeatureStoreError(
                f"Invalid JSON in feature file {path}: {exc}"
            ) from exc
        except OSError as exc:
            raise FeatureStoreError(
                f"Cannot read feature file {path}: {exc}"
            ) from exc

    def _entity_count(self) -> int:
        """Count total entities across all types."""
        return sum(len(v) for v in self._data.values())

    @staticmethod
    def _calculate_freshness(updated_at_str: str, now: datetime) -> float:
        """Calculate data freshness in seconds.

        Args:
            updated_at_str: ISO timestamp string.
            now: Current UTC time.

        Returns:
            Seconds since the data was last updated, or 0.0 if unknown.
        """
        if not updated_at_str:
            return 0.0
        try:
            updated_at = datetime.fromisoformat(
                updated_at_str.replace("Z", "+00:00")
            )
            delta = (now - updated_at).total_seconds()
            return max(0.0, delta)
        except (ValueError, TypeError):
            return 0.0


# ------------------------------------------------------------------
# Feast implementation (stub -- requires feast package)
# ------------------------------------------------------------------


class FeastClient:
    """Feast online store implementation.

    Requires the ``feast`` package to be installed.

    Args:
        repo_path: Path to the Feast repository directory.
        project: Feast project name.
    """

    def __init__(self, repo_path: str, project: str = "asahi") -> None:
        self._repo_path = repo_path
        self._project = project
        self._store: Optional[Any] = None
        self._init_store()

    def get_features(
        self,
        entity_id: str,
        entity_type: str,
        feature_names: List[str],
    ) -> FeatureVector:
        """Retrieve features from Feast online store.

        Args:
            entity_id: Entity identifier.
            entity_type: Entity category.
            feature_names: Feature references (e.g. ``"view:col"``).

        Returns:
            Populated :class:`FeatureVector`.

        Raises:
            FeatureStoreError: If Feast is not available or the query fails.
        """
        if self._store is None:
            raise FeatureStoreError("Feast store not initialised")

        now = datetime.now(timezone.utc)
        try:
            result = self._store.get_online_features(
                features=feature_names,
                entity_rows=[{entity_type + "_id": entity_id}],
            )
            features_dict = dict(zip(result.feature_names, result.feature_values))
            return FeatureVector(
                entity_id=entity_id,
                entity_type=entity_type,
                features=features_dict,
                retrieved_at=now,
                freshness_seconds=0.0,
                source="feast",
            )
        except Exception as exc:
            logger.error(
                "Feast feature fetch failed",
                extra={"entity_id": entity_id, "error": str(exc)},
                exc_info=True,
            )
            raise FeatureStoreError(f"Feast query failed: {exc}") from exc

    def get_batch_features(
        self,
        entity_ids: List[str],
        entity_type: str,
        feature_names: List[str],
    ) -> List[FeatureVector]:
        """Retrieve features for multiple entities from Feast.

        Args:
            entity_ids: List of entity identifiers.
            entity_type: Shared entity category.
            feature_names: Feature references.

        Returns:
            List of :class:`FeatureVector` objects.
        """
        return [
            self.get_features(eid, entity_type, feature_names)
            for eid in entity_ids
        ]

    def health_check(self) -> bool:
        """Check Feast connectivity.

        Returns:
            ``True`` if the Feast store is initialised.
        """
        return self._store is not None

    def _init_store(self) -> None:
        """Initialise the Feast FeatureStore client."""
        try:
            from feast import FeatureStore

            self._store = FeatureStore(repo_path=self._repo_path)
            logger.info(
                "Feast store initialised",
                extra={
                    "repo_path": self._repo_path,
                    "project": self._project,
                },
            )
        except ImportError:
            logger.warning(
                "Feast package not installed; FeastClient will not function"
            )
            self._store = None
        except Exception as exc:
            logger.error(
                "Failed to initialise Feast store",
                extra={"error": str(exc)},
                exc_info=True,
            )
            self._store = None

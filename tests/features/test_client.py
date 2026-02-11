"""Tests for FeatureStoreClient -- LocalFeatureStore and Protocol."""

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

import pytest

from src.exceptions import FeatureStoreError
from src.features.client import (
    FeatureStoreClient,
    FeatureStoreConfig,
    FeatureVector,
    LocalFeatureStore,
)


class TestFeatureStoreConfig:
    """Tests for FeatureStoreConfig defaults."""

    def test_default_values(self) -> None:
        cfg = FeatureStoreConfig()
        assert cfg.provider == "local"
        assert cfg.timeout_ms == 200
        assert cfg.fallback_on_timeout is True

    def test_custom_values(self) -> None:
        cfg = FeatureStoreConfig(provider="feast", timeout_ms=500)
        assert cfg.provider == "feast"
        assert cfg.timeout_ms == 500


class TestFeatureVector:
    """Tests for FeatureVector model."""

    def test_creation(self) -> None:
        vec = FeatureVector(
            entity_id="user-1",
            entity_type="user",
            features={"score": 0.8},
            source="local",
        )
        assert vec.entity_id == "user-1"
        assert vec.features["score"] == 0.8
        assert vec.source == "local"

    def test_defaults(self) -> None:
        vec = FeatureVector(entity_id="x", entity_type="product")
        assert vec.features == {}
        assert vec.freshness_seconds == 0.0


class TestLocalFeatureStore:
    """Tests for the JSON-file backed LocalFeatureStore."""

    @pytest.fixture
    def store(self) -> LocalFeatureStore:
        """Store pre-loaded with test entities."""
        store = LocalFeatureStore()
        now_iso = datetime.now(timezone.utc).isoformat()
        store.add_entity("user", "user-123", {
            "purchase_history": ["shoes", "jacket", "belt"],
            "preference_score": 0.8,
            "tier": "gold",
        })
        store.add_entity("user", "user-456", {
            "purchase_history": ["laptop"],
            "preference_score": 0.3,
            "tier": "silver",
        })
        store.add_entity("organization", "org-1", {
            "brand_voice": "professional",
            "industry": "fintech",
        })
        return store

    def test_get_features_existing(self, store: LocalFeatureStore) -> None:
        vec = store.get_features(
            "user-123", "user", ["purchase_history", "tier"]
        )
        assert vec.entity_id == "user-123"
        assert vec.features["tier"] == "gold"
        assert len(vec.features["purchase_history"]) == 3
        assert vec.source == "local"

    def test_get_features_missing_entity(self, store: LocalFeatureStore) -> None:
        vec = store.get_features("user-999", "user", ["tier"])
        assert vec.features == {}
        assert vec.entity_id == "user-999"

    def test_get_features_missing_feature_name(
        self, store: LocalFeatureStore
    ) -> None:
        vec = store.get_features("user-123", "user", ["nonexistent"])
        assert "nonexistent" not in vec.features

    def test_get_features_partial(self, store: LocalFeatureStore) -> None:
        vec = store.get_features(
            "user-123", "user", ["tier", "nonexistent"]
        )
        assert "tier" in vec.features
        assert "nonexistent" not in vec.features

    def test_get_batch_features(self, store: LocalFeatureStore) -> None:
        vecs = store.get_batch_features(
            ["user-123", "user-456"], "user", ["tier"]
        )
        assert len(vecs) == 2
        assert vecs[0].features["tier"] == "gold"
        assert vecs[1].features["tier"] == "silver"

    def test_get_batch_with_missing(self, store: LocalFeatureStore) -> None:
        vecs = store.get_batch_features(
            ["user-123", "user-999"], "user", ["tier"]
        )
        assert len(vecs) == 2
        assert vecs[0].features.get("tier") == "gold"
        assert vecs[1].features == {}

    def test_health_check(self, store: LocalFeatureStore) -> None:
        assert store.health_check() is True

    def test_add_entity(self, store: LocalFeatureStore) -> None:
        store.add_entity("product", "prod-1", {"price": 99.99})
        vec = store.get_features("prod-1", "product", ["price"])
        assert vec.features["price"] == 99.99

    def test_freshness_calculated(self, store: LocalFeatureStore) -> None:
        vec = store.get_features("user-123", "user", ["tier"])
        # Just added, so freshness should be very small
        assert vec.freshness_seconds < 5.0

    def test_organization_features(self, store: LocalFeatureStore) -> None:
        vec = store.get_features("org-1", "organization", ["brand_voice"])
        assert vec.features["brand_voice"] == "professional"
        assert vec.entity_type == "organization"


class TestLocalFeatureStoreFromFile:
    """Tests for loading LocalFeatureStore from JSON file."""

    def test_load_valid_json(self) -> None:
        data: Dict[str, Any] = {
            "user": {
                "u1": {
                    "tier": "gold",
                    "_updated_at": datetime.now(timezone.utc).isoformat(),
                }
            }
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(data, f)
            f.flush()
            path = Path(f.name)

        store = LocalFeatureStore(data_path=path)
        vec = store.get_features("u1", "user", ["tier"])
        assert vec.features["tier"] == "gold"
        path.unlink()

    def test_load_invalid_json_raises(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            f.write("not valid json {{{")
            f.flush()
            path = Path(f.name)

        with pytest.raises(FeatureStoreError, match="Invalid JSON"):
            LocalFeatureStore(data_path=path)
        path.unlink()

    def test_load_nonexistent_file(self) -> None:
        # Should not raise -- just start empty
        store = LocalFeatureStore(data_path=Path("/nonexistent/path.json"))
        assert store.health_check() is True


class TestProtocolCompliance:
    """Verify LocalFeatureStore satisfies FeatureStoreClient Protocol."""

    def test_local_store_is_protocol_compliant(self) -> None:
        store = LocalFeatureStore()
        assert isinstance(store, FeatureStoreClient)


class TestFeastClient:
    """Tests for FeastClient (without feast package installed)."""

    def test_feast_init_without_package(self) -> None:
        """FeastClient should handle missing feast package gracefully."""
        from src.features.client import FeastClient

        client = FeastClient(repo_path="/nonexistent", project="test")
        # Without feast installed, health_check should return False
        assert client.health_check() is False

    def test_feast_get_features_without_store_raises(self) -> None:
        from src.features.client import FeastClient

        client = FeastClient(repo_path="/nonexistent", project="test")
        with pytest.raises(FeatureStoreError, match="not initialised"):
            client.get_features("entity-1", "user", ["tier"])

    def test_feast_get_batch_without_store(self) -> None:
        from src.features.client import FeastClient

        client = FeastClient(repo_path="/nonexistent", project="test")
        # get_batch_features delegates to get_features which raises
        with pytest.raises(FeatureStoreError):
            client.get_batch_features(["e1"], "user", ["tier"])


class TestStaleData:
    """Tests for stale data handling."""

    def test_old_data_has_high_freshness(self) -> None:
        data: Dict[str, Any] = {
            "user": {
                "old-user": {
                    "tier": "bronze",
                    "_updated_at": (
                        datetime.now(timezone.utc) - timedelta(hours=2)
                    ).isoformat(),
                }
            }
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(data, f)
            f.flush()
            path = Path(f.name)

        store = LocalFeatureStore(data_path=path)
        vec = store.get_features("old-user", "user", ["tier"])
        assert vec.freshness_seconds > 7000  # > 2 hours in seconds
        path.unlink()

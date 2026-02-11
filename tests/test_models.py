"""
Tests for the Model Registry and ModelProfile.
"""

import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.exceptions import ConfigurationError, ModelNotFoundError
from src.models import ModelProfile, ModelRegistry, calculate_cost, estimate_tokens


# ---------------------------------------------------------------------------
# ModelProfile
# ---------------------------------------------------------------------------


class TestModelProfile:
    """Tests for ModelProfile Pydantic model."""

    def test_valid_profile_creation(self) -> None:
        profile = ModelProfile(
            name="test-model",
            provider="openai",
            api_key_env="TEST_KEY",
            cost_per_1k_input_tokens=0.01,
            cost_per_1k_output_tokens=0.03,
            avg_latency_ms=200,
            quality_score=4.5,
            max_input_tokens=128000,
            max_output_tokens=4096,
        )
        assert profile.name == "test-model"
        assert profile.provider == "openai"
        assert profile.availability == "available"

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ModelProfile(
                name="",
                provider="openai",
                api_key_env="KEY",
                cost_per_1k_input_tokens=0.01,
                cost_per_1k_output_tokens=0.03,
                avg_latency_ms=200,
                quality_score=4.5,
                max_input_tokens=128000,
                max_output_tokens=4096,
            )

    def test_negative_cost_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ModelProfile(
                name="model",
                provider="openai",
                api_key_env="KEY",
                cost_per_1k_input_tokens=-0.01,
                cost_per_1k_output_tokens=0.03,
                avg_latency_ms=200,
                quality_score=4.5,
                max_input_tokens=128000,
                max_output_tokens=4096,
            )

    def test_quality_score_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ModelProfile(
                name="model",
                provider="openai",
                api_key_env="KEY",
                cost_per_1k_input_tokens=0.01,
                cost_per_1k_output_tokens=0.03,
                avg_latency_ms=200,
                quality_score=6.0,
                max_input_tokens=128000,
                max_output_tokens=4096,
            )

    def test_zero_latency_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ModelProfile(
                name="model",
                provider="openai",
                api_key_env="KEY",
                cost_per_1k_input_tokens=0.01,
                cost_per_1k_output_tokens=0.03,
                avg_latency_ms=0,
                quality_score=4.0,
                max_input_tokens=128000,
                max_output_tokens=4096,
            )


# ---------------------------------------------------------------------------
# ModelRegistry
# ---------------------------------------------------------------------------


class TestModelRegistry:
    """Tests for ModelRegistry."""

    @pytest.fixture
    def registry(self) -> ModelRegistry:
        """Create a registry with defaults (no YAML)."""
        return ModelRegistry()

    @pytest.fixture
    def sample_profile(self) -> ModelProfile:
        return ModelProfile(
            name="test-model",
            provider="openai",
            api_key_env="TEST_KEY",
            cost_per_1k_input_tokens=0.005,
            cost_per_1k_output_tokens=0.015,
            avg_latency_ms=100,
            quality_score=3.8,
            max_input_tokens=32000,
            max_output_tokens=2048,
        )

    def test_defaults_loaded(self, registry: ModelRegistry) -> None:
        models = registry.all()
        assert len(models) >= 3
        names = {m.name for m in models}
        assert "gpt-4-turbo" in names
        assert "claude-3-5-sonnet" in names

    def test_add_and_get(
        self, registry: ModelRegistry, sample_profile: ModelProfile
    ) -> None:
        registry.add(sample_profile)
        retrieved = registry.get("test-model")
        assert retrieved.name == "test-model"
        assert retrieved.quality_score == 3.8

    def test_get_missing_raises(self, registry: ModelRegistry) -> None:
        with pytest.raises(ModelNotFoundError):
            registry.get("nonexistent-model")

    def test_remove(
        self, registry: ModelRegistry, sample_profile: ModelProfile
    ) -> None:
        registry.add(sample_profile)
        registry.remove("test-model")
        with pytest.raises(ModelNotFoundError):
            registry.get("test-model")

    def test_remove_missing_raises(self, registry: ModelRegistry) -> None:
        with pytest.raises(ModelNotFoundError):
            registry.remove("nonexistent-model")

    def test_filter_by_quality(self, registry: ModelRegistry) -> None:
        results = registry.filter(min_quality=4.5)
        assert all(m.quality_score >= 4.5 for m in results)
        assert len(results) >= 1

    def test_filter_by_latency(self, registry: ModelRegistry) -> None:
        results = registry.filter(max_latency_ms=160)
        assert all(m.avg_latency_ms <= 160 for m in results)

    def test_filter_returns_empty(self, registry: ModelRegistry) -> None:
        results = registry.filter(min_quality=5.0, max_latency_ms=1)
        assert results == []

    def test_contains(self, registry: ModelRegistry) -> None:
        assert "gpt-4-turbo" in registry
        assert "nonexistent" not in registry

    def test_len(self, registry: ModelRegistry) -> None:
        assert len(registry) >= 3

    def test_to_dict(self, registry: ModelRegistry) -> None:
        data = registry.to_dict()
        assert "models" in data
        assert "count" in data
        assert data["count"] == len(data["models"])

    def test_load_from_yaml(self) -> None:
        yaml_content = """
models:
  test-model-yaml:
    provider: openai
    api_key_env: TEST_KEY
    cost_per_1k_input_tokens: 0.005
    cost_per_1k_output_tokens: 0.015
    avg_latency_ms: 100
    quality_score: 3.8
    max_input_tokens: 32000
    max_output_tokens: 2048
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(yaml_content)
            f.flush()
            registry = ModelRegistry(config_path=Path(f.name))

        assert "test-model-yaml" in registry
        profile = registry.get("test-model-yaml")
        assert profile.provider == "openai"

    def test_load_from_yaml_invalid_raises(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("models:\n  bad-model:\n    provider: invalid_provider\n")
            f.flush()
            with pytest.raises(ConfigurationError):
                ModelRegistry(config_path=Path(f.name))

    def test_load_from_yaml_missing_file_raises(self) -> None:
        with pytest.raises(ConfigurationError):
            registry = ModelRegistry.__new__(ModelRegistry)
            registry._models = {}
            registry.load_from_yaml(Path("/nonexistent/path.yaml"))

    def test_duplicate_add_overwrites(
        self, registry: ModelRegistry, sample_profile: ModelProfile
    ) -> None:
        registry.add(sample_profile)
        updated = sample_profile.model_copy(update={"quality_score": 4.9})
        registry.add(updated)
        assert registry.get("test-model").quality_score == 4.9


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


class TestEstimateTokens:
    """Tests for the estimate_tokens utility."""

    def test_empty_string(self) -> None:
        assert estimate_tokens("") == 0

    def test_whitespace_only(self) -> None:
        assert estimate_tokens("   ") == 0

    def test_single_word(self) -> None:
        result = estimate_tokens("Hello")
        assert result >= 1

    def test_longer_text(self) -> None:
        result = estimate_tokens("This is a longer sentence with more words")
        assert result > 5

    def test_proportional(self) -> None:
        short = estimate_tokens("Hello world")
        long = estimate_tokens("Hello world " * 100)
        assert long > short


class TestCalculateCost:
    """Tests for the calculate_cost utility."""

    def test_basic_cost(self) -> None:
        profile = ModelProfile(
            name="test",
            provider="openai",
            api_key_env="KEY",
            cost_per_1k_input_tokens=0.010,
            cost_per_1k_output_tokens=0.030,
            avg_latency_ms=200,
            quality_score=4.0,
            max_input_tokens=128000,
            max_output_tokens=4096,
        )
        cost = calculate_cost(profile, input_tokens=1000, output_tokens=1000)
        assert cost == pytest.approx(0.040, abs=1e-6)

    def test_zero_tokens(self) -> None:
        profile = ModelProfile(
            name="test",
            provider="openai",
            api_key_env="KEY",
            cost_per_1k_input_tokens=0.010,
            cost_per_1k_output_tokens=0.030,
            avg_latency_ms=200,
            quality_score=4.0,
            max_input_tokens=128000,
            max_output_tokens=4096,
        )
        assert calculate_cost(profile, 0, 0) == 0.0

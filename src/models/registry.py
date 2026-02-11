"""
Model profiles and registry for Asahi inference optimizer.

Provides the ModelProfile Pydantic model and the ModelRegistry class,
which is the single source of truth for every LLM model the platform
can route to.  All other components query this registry -- they never
hard-code model information.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import yaml
from pydantic import BaseModel, Field, field_validator

from src.exceptions import ConfigurationError, ModelNotFoundError

logger = logging.getLogger(__name__)

# Default config path (relative to project root)
DEFAULT_MODELS_CONFIG = Path("config/models.yaml")


class ModelProfile(BaseModel):
    """Metadata for a single LLM model.

    Attributes:
        name: Canonical model identifier, e.g. ``claude-3-5-sonnet``.
        provider: Which SDK/adapter to use for inference.
        api_key_env: Environment variable name holding the API secret.
        cost_per_1k_input_tokens: Dollar cost per 1 000 input tokens.
        cost_per_1k_output_tokens: Dollar cost per 1 000 output tokens.
        avg_latency_ms: Expected p50 latency in milliseconds.
        quality_score: Benchmark quality rating (0.0 -- 5.0).
        max_input_tokens: Maximum context window size.
        max_output_tokens: Maximum generation length.
        description: Human-readable note about the model.
        availability: Runtime health status.
    """

    name: str
    provider: Literal["openai", "anthropic", "mistral", "local"] = "openai"
    api_key_env: str = "OPENAI_API_KEY"
    cost_per_1k_input_tokens: float = Field(ge=0.0)
    cost_per_1k_output_tokens: float = Field(ge=0.0)
    avg_latency_ms: int = Field(gt=0)
    quality_score: float = Field(ge=0.0, le=5.0)
    max_input_tokens: int = Field(gt=0)
    max_output_tokens: int = Field(gt=0)
    description: str = ""
    availability: Literal["available", "degraded", "unavailable"] = "available"

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        """Validate that model name is not blank."""
        if not v or not v.strip():
            raise ValueError("Model name must not be empty")
        return v.strip()


class ModelRegistry:
    """Single source of truth for all LLM model profiles.

    Args:
        config_path: Optional path to a YAML file containing model definitions.
            If provided and the file exists, models are loaded from it.
            If ``None``, built-in defaults are registered.
    """

    def __init__(self, config_path: Optional[Path] = None) -> None:
        self._models: Dict[str, ModelProfile] = {}

        if config_path is not None:
            self.load_from_yaml(config_path)
        elif DEFAULT_MODELS_CONFIG.exists():
            self.load_from_yaml(DEFAULT_MODELS_CONFIG)
        else:
            self._register_defaults()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, profile: ModelProfile) -> None:
        """Register or update a model profile.

        Args:
            profile: The model profile to register.
        """
        if profile.name in self._models:
            logger.warning(
                "Overwriting existing model",
                extra={"model": profile.name},
            )
        self._models[profile.name] = profile
        logger.info("Model registered", extra={"model": profile.name})

    def get(self, name: str) -> ModelProfile:
        """Return a model profile by name.

        Args:
            name: Canonical model identifier.

        Returns:
            The matching ModelProfile.

        Raises:
            ModelNotFoundError: If no model with that name is registered.
        """
        if name not in self._models:
            raise ModelNotFoundError(
                f"Model '{name}' not found in registry. "
                f"Available: {list(self._models.keys())}"
            )
        return self._models[name]

    def remove(self, name: str) -> None:
        """De-register a model.

        Args:
            name: Model to remove.

        Raises:
            ModelNotFoundError: If the model is not registered.
        """
        if name not in self._models:
            raise ModelNotFoundError(f"Cannot remove unknown model '{name}'")
        del self._models[name]
        logger.info("Model removed", extra={"model": name})

    def all(self) -> List[ModelProfile]:
        """Return all registered model profiles."""
        return list(self._models.values())

    def filter(
        self,
        min_quality: float = 0.0,
        max_latency_ms: int = 99999,
    ) -> List[ModelProfile]:
        """Return profiles meeting quality and latency constraints.

        Args:
            min_quality: Minimum quality score (inclusive).
            max_latency_ms: Maximum average latency (inclusive).

        Returns:
            List of matching profiles (may be empty).
        """
        return [
            p
            for p in self._models.values()
            if p.quality_score >= min_quality
            and p.avg_latency_ms <= max_latency_ms
            and p.availability != "unavailable"
        ]

    def load_from_yaml(self, path: Path) -> None:
        """Parse a YAML config file and register all models found.

        Args:
            path: Path to the YAML file.

        Raises:
            ConfigurationError: If the file cannot be read or parsed.
        """
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
        except FileNotFoundError as exc:
            raise ConfigurationError(
                f"Models config file not found: {path}"
            ) from exc
        except yaml.YAMLError as exc:
            raise ConfigurationError(
                f"Invalid YAML in {path}: {exc}"
            ) from exc

        if not data or "models" not in data:
            raise ConfigurationError(
                f"Expected top-level 'models' key in {path}"
            )

        for name, fields in data["models"].items():
            try:
                profile = ModelProfile(name=name, **fields)
                self.add(profile)
            except Exception as exc:
                logger.error(
                    "Failed to load model from config",
                    extra={"model": name, "error": str(exc)},
                )
                raise ConfigurationError(
                    f"Invalid model definition for '{name}' in {path}: {exc}"
                ) from exc

        logger.info(
            "Models loaded from YAML",
            extra={"path": str(path), "count": len(self._models)},
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the registry for API responses.

        Returns:
            Dict with ``models`` list and ``count``.
        """
        return {
            "models": [
                {"name": p.name, **p.model_dump(exclude={"name"})}
                for p in self._models.values()
            ],
            "count": len(self._models),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _register_defaults(self) -> None:
        """Register hard-coded default models (fallback when no YAML exists)."""
        defaults = [
            ModelProfile(
                name="gpt-4-turbo",
                provider="openai",
                api_key_env="OPENAI_API_KEY",
                cost_per_1k_input_tokens=0.010,
                cost_per_1k_output_tokens=0.030,
                avg_latency_ms=200,
                quality_score=4.6,
                max_input_tokens=128000,
                max_output_tokens=4096,
                description="Most powerful OpenAI model, highest quality",
            ),
            ModelProfile(
                name="claude-opus-4",
                provider="anthropic",
                api_key_env="ANTHROPIC_API_KEY",
                cost_per_1k_input_tokens=0.015,
                cost_per_1k_output_tokens=0.075,
                avg_latency_ms=180,
                quality_score=4.5,
                max_input_tokens=200000,
                max_output_tokens=4096,
                description="High quality Anthropic model, moderate cost",
            ),
            ModelProfile(
                name="claude-3-5-sonnet",
                provider="anthropic",
                api_key_env="ANTHROPIC_API_KEY",
                cost_per_1k_input_tokens=0.003,
                cost_per_1k_output_tokens=0.015,
                avg_latency_ms=150,
                quality_score=4.1,
                max_input_tokens=200000,
                max_output_tokens=4096,
                description="Fast, cheap, reasonable quality",
            ),
        ]
        for profile in defaults:
            self.add(profile)

    def __len__(self) -> int:
        return len(self._models)

    def __contains__(self, name: str) -> bool:
        return name in self._models


def estimate_tokens(text: str) -> int:
    """Quick token estimate based on whitespace splitting.

    Uses the approximation of ~1.3 tokens per whitespace-delimited word.

    Args:
        text: Input text to estimate.

    Returns:
        Estimated token count (minimum 1 for non-empty text, 0 for empty).
    """
    if not text or not text.strip():
        return 0
    return max(1, int(len(text.split()) * 1.3))


def calculate_cost(
    model: ModelProfile,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Calculate the dollar cost for a given token count and model.

    Args:
        model: The model profile containing pricing data.
        input_tokens: Number of input tokens.
        output_tokens: Number of output tokens.

    Returns:
        Dollar cost rounded to 6 decimal places.
    """
    input_cost = (input_tokens / 1000) * model.cost_per_1k_input_tokens
    output_cost = (output_tokens / 1000) * model.cost_per_1k_output_tokens
    return round(input_cost + output_cost, 6)

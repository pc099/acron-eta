"""
Asahi exception hierarchy.

All custom exceptions inherit from AsahiException so callers can
catch a single base type when they want a broad safety net.
"""


class AsahiException(Exception):
    """Base exception for all Asahi errors."""


class ConfigurationError(AsahiException, ValueError):
    """Raised when configuration is invalid or cannot be loaded."""


class ModelNotFoundError(AsahiException, KeyError):
    """Raised when a requested model is not in the registry."""


class NoModelsAvailableError(AsahiException):
    """Raised when the registry contains zero models."""


class ProviderError(AsahiException):
    """Raised when an LLM provider call fails after retries."""


class EmbeddingError(AsahiException):
    """Raised when an embedding operation fails."""


class VectorDBError(AsahiException):
    """Raised when a vector database operation fails."""


class BatchingError(AsahiException):
    """Raised when a batching operation fails."""


class FeatureConfigError(AsahiException, ValueError):
    """Raised when feature store configuration or feature names are invalid."""


class FeatureStoreError(AsahiException):
    """Raised when a feature store operation fails."""


class ObservabilityError(AsahiException):
    """Raised when a metrics, analytics, or forecasting operation fails."""

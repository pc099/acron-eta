"""
Central configuration loader for Asahi inference optimizer.

Reads ``config/config.yaml`` and ``.env``, merges environment-variable
overrides (``ASAHI_`` prefix), and exposes a typed :class:`Settings`
singleton via :func:`get_settings`.
"""

import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Resolve project root (directory containing ``config/``)
# ---------------------------------------------------------------------------

_THIS_DIR = Path(__file__).resolve().parent          # src/
_PROJECT_ROOT = _THIS_DIR.parent                     # repo root


def _project_path(*parts: str) -> Path:
    """Build an absolute path relative to the project root."""
    return _PROJECT_ROOT.joinpath(*parts)


# ---------------------------------------------------------------------------
# Nested settings dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ApiSettings:
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: List[str] = field(default_factory=lambda: ["*"])
    rate_limit_per_minute: int = 100
    version: str = "1.0.0"
    baseline_input_rate: float = 0.010
    baseline_output_rate: float = 0.030


@dataclass
class CacheSettings:
    ttl_seconds: int = 86400
    max_entries: int = 10000
    cleanup_interval_seconds: int = 300


@dataclass
class RoutingSettings:
    default_quality_threshold: float = 3.5
    default_latency_budget_ms: int = 300
    quality_map: Dict[str, float] = field(default_factory=lambda: {
        "low": 3.0, "medium": 3.5, "high": 4.0, "max": 4.5,
    })
    latency_map: Dict[str, int] = field(default_factory=lambda: {
        "slow": 2000, "normal": 500, "fast": 300, "instant": 150,
    })
    task_overrides: Dict[str, Dict[str, float]] = field(default_factory=lambda: {
        "coding": {"min_quality": 4.0, "max_latency": 500},
        "reasoning": {"min_quality": 4.0, "max_latency": 500},
        "legal": {"min_quality": 4.2, "max_latency": 2000},
    })


@dataclass
class TrackingSettings:
    log_dir: str = "data/logs"
    enable_kafka: bool = False
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic: str = "asahi_inference_events"
    baseline_input_rate: float = 0.010
    baseline_output_rate: float = 0.030


@dataclass
class AnomalySettings:
    cost_spike_threshold: float = 2.0
    latency_spike_threshold: float = 2.0
    error_rate_threshold: float = 0.01
    cache_degradation_threshold: float = 0.5
    quality_drop_threshold: float = 0.5
    rolling_window_hours: int = 24


@dataclass
class ForecastSettings:
    ema_span_days: int = 7
    min_data_points: int = 3
    stable_threshold_pct: float = 5.0


@dataclass
class ObservabilitySettings:
    enabled: bool = True
    prometheus_port: int = 9090
    collection_interval_seconds: int = 10
    retention_hours: int = 168
    export_format: str = "prometheus"
    anomaly: AnomalySettings = field(default_factory=AnomalySettings)
    forecasting: ForecastSettings = field(default_factory=ForecastSettings)


@dataclass
class EmbeddingsSettings:
    provider: str = "cohere"
    model_name: str = "embed-english-v3.0"
    api_key_env: str = "COHERE_API_KEY"
    dimension: int = 1024
    batch_size: int = 96
    timeout_seconds: int = 30
    max_retries: int = 3


@dataclass
class BatchingSettings:
    min_batch_size: int = 2
    max_batch_size: int = 10
    max_wait_ms: int = 500
    latency_threshold_ms: int = 200
    eligible_task_types: List[str] = field(
        default_factory=lambda: ["summarization", "faq", "translation"]
    )


@dataclass
class FeatureStoreSettings:
    provider: str = "local"
    local_data_path: str = "data/features.json"
    timeout_ms: int = 200
    fallback_on_timeout: bool = True
    freshness_threshold_seconds: int = 3600
    max_feature_tokens: int = 200


@dataclass
class OptimizationSettings:
    min_relevance_threshold: float = 0.3
    scoring_method: str = "keyword"
    max_history_turns: int = 5
    extractive_top_ratio: float = 0.5
    max_few_shot_examples: int = 3
    max_quality_risk: str = "medium"


@dataclass
class GovernanceSettings:
    encryption_key_env: str = "ASAHI_ENCRYPTION_KEY"
    pbkdf2_iterations: int = 480000
    salt_length: int = 16
    audit_storage_dir: str = "data/audit"
    audit_max_entries: int = 10000
    audit_enable_hash_chain: bool = True
    auth_api_key_required: bool = False
    auth_key_expiry_days: int = 90
    auth_key_prefix: str = "ask"
    budget_tracking_window_hours: int = 24
    default_max_requests_per_day: int = 1000
    tenancy_cache_namespace_prefix: str = "tenant"
    compliance_pii_detection: bool = True
    compliance_default_retention_days: int = 365


@dataclass
class LoggingSettings:
    level: str = "INFO"
    format: str = "json"


@dataclass
class Settings:
    """Top-level settings container."""
    api: ApiSettings = field(default_factory=ApiSettings)
    cache: CacheSettings = field(default_factory=CacheSettings)
    routing: RoutingSettings = field(default_factory=RoutingSettings)
    tracking: TrackingSettings = field(default_factory=TrackingSettings)
    observability: ObservabilitySettings = field(default_factory=ObservabilitySettings)
    embeddings: EmbeddingsSettings = field(default_factory=EmbeddingsSettings)
    batching: BatchingSettings = field(default_factory=BatchingSettings)
    feature_store: FeatureStoreSettings = field(default_factory=FeatureStoreSettings)
    optimization: OptimizationSettings = field(default_factory=OptimizationSettings)
    governance: GovernanceSettings = field(default_factory=GovernanceSettings)
    logging: LoggingSettings = field(default_factory=LoggingSettings)


# ---------------------------------------------------------------------------
# YAML loader
# ---------------------------------------------------------------------------

def _load_yaml(path: Path) -> Dict[str, Any]:
    """Read and parse a YAML file.  Returns ``{}`` if the file is missing."""
    if not path.exists():
        logger.warning("Config file not found: %s", path)
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data if isinstance(data, dict) else {}


def _apply_dict(target: object, data: Dict[str, Any]) -> None:
    """Recursively apply *data* values onto a dataclass instance."""
    for key, value in data.items():
        if not hasattr(target, key):
            continue
        current = getattr(target, key)
        if isinstance(current, (AnomalySettings, ForecastSettings)) and isinstance(value, dict):
            _apply_dict(current, value)
        else:
            setattr(target, key, value)


# ---------------------------------------------------------------------------
# Env-var overrides  (ASAHI_SECTION_KEY  e.g. ASAHI_API_PORT)
# ---------------------------------------------------------------------------

_FLAT_SECTIONS = [
    "api", "cache", "routing", "tracking", "observability",
    "embeddings", "batching", "feature_store", "optimization",
    "governance", "logging",
]

_TYPE_MAP = {
    int: int,
    float: float,
    bool: lambda v: v.lower() in ("1", "true", "yes"),
    str: str,
}


def _apply_env_overrides(settings: Settings) -> None:
    """Override flat scalar fields via ``ASAHI_<SECTION>_<KEY>`` env vars."""
    for section_name in _FLAT_SECTIONS:
        section = getattr(settings, section_name, None)
        if section is None:
            continue
        prefix = f"ASAHI_{section_name.upper()}_"
        for key in list(vars(section)):
            env_key = prefix + key.upper()
            env_val = os.environ.get(env_key)
            if env_val is None:
                continue
            current = getattr(section, key)
            cast = _TYPE_MAP.get(type(current), str)
            try:
                setattr(section, key, cast(env_val))
                logger.debug("Env override applied: %s=%s", env_key, env_val)
            except (ValueError, TypeError):
                logger.warning("Invalid env override %s=%s", env_key, env_val)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_settings: Optional[Settings] = None
_lock = threading.Lock()


def get_settings(
    *,
    yaml_path: Optional[Path] = None,
    env_path: Optional[Path] = None,
    _force_reload: bool = False,
) -> Settings:
    """Return the application-wide :class:`Settings` singleton.

    On first call (or when ``_force_reload=True``) the function:

    1. Calls ``load_dotenv()`` to populate env vars from ``.env``.
    2. Reads ``config/config.yaml``.
    3. Applies ``ASAHI_*`` environment-variable overrides.

    Args:
        yaml_path: Override the YAML config file path (testing).
        env_path: Override the ``.env`` file path (testing).
        _force_reload: Re-read everything even if already loaded.

    Returns:
        The global ``Settings`` instance.
    """
    global _settings

    if _settings is not None and not _force_reload:
        return _settings

    with _lock:
        # Double-check after acquiring lock
        if _settings is not None and not _force_reload:
            return _settings

        # 1. Load .env
        dotenv_path = env_path or _project_path(".env")
        load_dotenv(dotenv_path, override=True)

        # 2. Read YAML
        config_path = yaml_path or _project_path("config", "config.yaml")
        raw = _load_yaml(config_path)

        # 3. Build Settings with defaults, then overlay YAML values
        settings = Settings()

        for section_name in _FLAT_SECTIONS:
            section_data = raw.get(section_name)
            if isinstance(section_data, dict):
                section_obj = getattr(settings, section_name)
                _apply_dict(section_obj, section_data)

        # Handle nested observability sub-sections from YAML
        obs_data = raw.get("observability", {})
        if isinstance(obs_data, dict):
            anomaly_data = obs_data.get("anomaly")
            if isinstance(anomaly_data, dict):
                _apply_dict(settings.observability.anomaly, anomaly_data)
            forecast_data = obs_data.get("forecasting")
            if isinstance(forecast_data, dict):
                _apply_dict(settings.observability.forecasting, forecast_data)

        # 4. Apply ASAHI_* env-var overrides
        _apply_env_overrides(settings)

        _settings = settings
        logger.info("Settings loaded from %s", config_path)
        return _settings


def reset_settings() -> None:
    """Clear the cached singleton (for testing)."""
    global _settings
    with _lock:
        _settings = None

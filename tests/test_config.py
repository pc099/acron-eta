"""Tests for the central configuration loader (src/config.py)."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from src.config import (
    Settings,
    get_settings,
    reset_settings,
    _load_yaml,
    _apply_dict,
    _apply_env_overrides,
    ApiSettings,
    CacheSettings,
    RoutingSettings,
    TrackingSettings,
    ObservabilitySettings,
    GovernanceSettings,
)


@pytest.fixture(autouse=True)
def _clean_settings():
    """Reset the singleton before and after each test."""
    reset_settings()
    yield
    reset_settings()


# ── YAML loading ────────────────────────────────────────


class TestLoadYaml:
    def test_loads_valid_yaml(self, tmp_path):
        f = tmp_path / "cfg.yaml"
        f.write_text("api:\n  port: 9999\n")
        data = _load_yaml(f)
        assert data["api"]["port"] == 9999

    def test_returns_empty_dict_for_missing_file(self, tmp_path):
        data = _load_yaml(tmp_path / "nonexistent.yaml")
        assert data == {}

    def test_returns_empty_dict_for_non_dict_yaml(self, tmp_path):
        f = tmp_path / "cfg.yaml"
        f.write_text("- item1\n- item2\n")
        data = _load_yaml(f)
        assert data == {}


# ── Settings defaults ───────────────────────────────────


class TestSettingsDefaults:
    def test_default_settings_have_expected_values(self):
        s = Settings()
        assert s.api.port == 8000
        assert s.cache.ttl_seconds == 86400
        assert s.routing.default_quality_threshold == 3.5
        assert s.tracking.baseline_input_rate == 0.010
        assert s.tracking.baseline_output_rate == 0.030
        assert s.observability.anomaly.cost_spike_threshold == 2.0
        assert s.governance.auth_api_key_required is False


# ── get_settings() from YAML ────────────────────────────


class TestGetSettings:
    def _write_config(self, tmp_path, data):
        f = tmp_path / "config.yaml"
        f.write_text(yaml.dump(data))
        return f

    def test_loads_yaml_values(self, tmp_path):
        cfg = self._write_config(tmp_path, {
            "api": {"port": 7777},
            "cache": {"ttl_seconds": 1234},
        })
        s = get_settings(yaml_path=cfg, _force_reload=True)
        assert s.api.port == 7777
        assert s.cache.ttl_seconds == 1234

    def test_missing_yaml_uses_defaults(self, tmp_path):
        missing = tmp_path / "nope.yaml"
        s = get_settings(yaml_path=missing, _force_reload=True)
        assert s.api.port == 8000

    def test_singleton_returns_same_object(self, tmp_path):
        cfg = self._write_config(tmp_path, {"api": {"port": 5555}})
        s1 = get_settings(yaml_path=cfg, _force_reload=True)
        s2 = get_settings()
        assert s1 is s2

    def test_force_reload_reloads(self, tmp_path):
        cfg = self._write_config(tmp_path, {"api": {"port": 1111}})
        s1 = get_settings(yaml_path=cfg, _force_reload=True)
        assert s1.api.port == 1111

        cfg.write_text(yaml.dump({"api": {"port": 2222}}))
        s2 = get_settings(yaml_path=cfg, _force_reload=True)
        assert s2.api.port == 2222

    def test_nested_observability_anomaly(self, tmp_path):
        cfg = self._write_config(tmp_path, {
            "observability": {
                "enabled": False,
                "anomaly": {"cost_spike_threshold": 5.0},
                "forecasting": {"ema_span_days": 14},
            }
        })
        s = get_settings(yaml_path=cfg, _force_reload=True)
        assert s.observability.enabled is False
        assert s.observability.anomaly.cost_spike_threshold == 5.0
        assert s.observability.forecasting.ema_span_days == 14

    def test_routing_maps_from_yaml(self, tmp_path):
        cfg = self._write_config(tmp_path, {
            "routing": {
                "quality_map": {"low": 2.0, "medium": 3.0},
                "latency_map": {"slow": 3000},
            }
        })
        s = get_settings(yaml_path=cfg, _force_reload=True)
        assert s.routing.quality_map["low"] == 2.0
        assert s.routing.latency_map["slow"] == 3000


# ── Environment variable overrides ──────────────────────


class TestEnvOverrides:
    def test_env_override_int(self, tmp_path, monkeypatch):
        cfg = self._write_config(tmp_path, {"api": {"port": 8000}})
        monkeypatch.setenv("ASAHI_API_PORT", "9999")
        s = get_settings(yaml_path=cfg, _force_reload=True)
        assert s.api.port == 9999

    def test_env_override_float(self, tmp_path, monkeypatch):
        cfg = self._write_config(tmp_path, {})
        monkeypatch.setenv("ASAHI_ROUTING_DEFAULT_QUALITY_THRESHOLD", "4.2")
        s = get_settings(yaml_path=cfg, _force_reload=True)
        assert s.routing.default_quality_threshold == 4.2

    def test_env_override_bool(self, tmp_path, monkeypatch):
        cfg = self._write_config(tmp_path, {})
        monkeypatch.setenv("ASAHI_OBSERVABILITY_ENABLED", "false")
        s = get_settings(yaml_path=cfg, _force_reload=True)
        assert s.observability.enabled is False

    def test_env_override_string(self, tmp_path, monkeypatch):
        cfg = self._write_config(tmp_path, {})
        monkeypatch.setenv("ASAHI_TRACKING_LOG_DIR", "/custom/logs")
        s = get_settings(yaml_path=cfg, _force_reload=True)
        assert s.tracking.log_dir == "/custom/logs"

    def test_env_overrides_trump_yaml(self, tmp_path, monkeypatch):
        cfg = self._write_config(tmp_path, {"api": {"port": 3000}})
        monkeypatch.setenv("ASAHI_API_PORT", "4000")
        s = get_settings(yaml_path=cfg, _force_reload=True)
        assert s.api.port == 4000

    def _write_config(self, tmp_path, data):
        f = tmp_path / "config.yaml"
        f.write_text(yaml.dump(data))
        return f


# ── _apply_dict helper ──────────────────────────────────


class TestApplyDict:
    def test_applies_known_keys(self):
        target = ApiSettings()
        _apply_dict(target, {"port": 1234, "host": "localhost"})
        assert target.port == 1234
        assert target.host == "localhost"

    def test_ignores_unknown_keys(self):
        target = ApiSettings()
        _apply_dict(target, {"unknown_field": "value"})
        assert target.port == 8000  # unchanged


# ── Integration: real config/config.yaml ─────────────────


class TestRealConfig:
    def test_loads_project_config_yaml(self):
        """Verify that the actual config/config.yaml is loaded correctly."""
        s = get_settings(_force_reload=True)
        # These values match config/config.yaml
        assert s.cache.ttl_seconds == 86400
        assert s.batching.max_batch_size == 10
        assert s.observability.retention_hours == 168
        assert s.tracking.baseline_input_rate == 0.010
        assert s.governance.pbkdf2_iterations == 480000

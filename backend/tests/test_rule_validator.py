"""Tests for the routing rule validator service."""

import pytest

from app.services.rule_validator import validate_rule


class TestStepBasedValidation:
    """Tests for step_based rule validation."""

    def test_valid_step_based(self) -> None:
        errors = validate_rule("step_based", {
            "rules": [
                {"step": 1, "model": "gpt-4o-mini"},
                {"step": 3, "model": "gpt-4-turbo"},
            ]
        })
        assert errors == []

    def test_missing_rules_list(self) -> None:
        errors = validate_rule("step_based", {})
        assert any("rules" in e for e in errors)

    def test_negative_step(self) -> None:
        errors = validate_rule("step_based", {
            "rules": [{"step": -1, "model": "gpt-4o-mini"}]
        })
        assert any("positive integer" in e for e in errors)

    def test_duplicate_step(self) -> None:
        errors = validate_rule("step_based", {
            "rules": [
                {"step": 1, "model": "gpt-4o-mini"},
                {"step": 1, "model": "gpt-4-turbo"},
            ]
        })
        assert any("Duplicate" in e for e in errors)

    def test_unknown_model(self) -> None:
        errors = validate_rule("step_based", {
            "rules": [{"step": 1, "model": "nonexistent-model"}]
        })
        assert any("Unknown model" in e for e in errors)


class TestTimeBasedValidation:
    """Tests for time_based rule validation."""

    def test_valid_time_based(self) -> None:
        errors = validate_rule("time_based", {
            "rules": [
                {"hours": "0-8", "model": "gpt-4o-mini"},
                {"hours": "9-17", "model": "gpt-4-turbo"},
                {"hours": "18-23", "model": "gpt-4o-mini"},
            ]
        })
        assert errors == []

    def test_invalid_hours_format(self) -> None:
        errors = validate_rule("time_based", {
            "rules": [{"hours": "abc", "model": "gpt-4o-mini"}]
        })
        assert len(errors) > 0

    def test_hours_out_of_range(self) -> None:
        errors = validate_rule("time_based", {
            "rules": [{"hours": "0-25", "model": "gpt-4o-mini"}]
        })
        assert any("0-23" in e for e in errors)

    def test_overlapping_ranges(self) -> None:
        errors = validate_rule("time_based", {
            "rules": [
                {"hours": "0-12", "model": "gpt-4o-mini"},
                {"hours": "10-20", "model": "gpt-4-turbo"},
            ]
        })
        assert any("Overlapping" in e for e in errors)

    def test_midnight_wrap(self) -> None:
        errors = validate_rule("time_based", {
            "rules": [{"hours": "22-6", "model": "gpt-4o-mini"}]
        })
        assert errors == []


class TestFallbackChainValidation:
    """Tests for fallback_chain rule validation."""

    def test_valid_chain(self) -> None:
        errors = validate_rule("fallback_chain", {
            "chain": ["gpt-4-turbo", "gpt-4o-mini"]
        })
        assert errors == []

    def test_chain_too_short(self) -> None:
        errors = validate_rule("fallback_chain", {
            "chain": ["gpt-4-turbo"]
        })
        assert any("at least 2" in e for e in errors)

    def test_chain_with_unknown_model(self) -> None:
        errors = validate_rule("fallback_chain", {
            "chain": ["gpt-4-turbo", "nonexistent"]
        })
        assert any("Unknown model" in e for e in errors)

    def test_chain_with_duplicates(self) -> None:
        errors = validate_rule("fallback_chain", {
            "chain": ["gpt-4-turbo", "gpt-4-turbo"]
        })
        assert any("duplicate" in e for e in errors)

    def test_missing_chain_list(self) -> None:
        errors = validate_rule("fallback_chain", {})
        assert any("chain" in e for e in errors)


class TestOtherRuleTypes:
    """Tests for cost_ceiling, model_allowlist, provider_restriction."""

    def test_valid_cost_ceiling(self) -> None:
        errors = validate_rule("cost_ceiling_per_1k", {"value": 0.01})
        assert errors == []

    def test_negative_cost_ceiling(self) -> None:
        errors = validate_rule("cost_ceiling_per_1k", {"value": -1.0})
        assert any("positive" in e for e in errors)

    def test_missing_cost_ceiling_value(self) -> None:
        errors = validate_rule("cost_ceiling_per_1k", {})
        assert any("value" in e for e in errors)

    def test_valid_allowlist(self) -> None:
        errors = validate_rule("model_allowlist", {"models": ["gpt-4-turbo", "gpt-4o"]})
        assert errors == []

    def test_allowlist_unknown_model(self) -> None:
        errors = validate_rule("model_allowlist", {"models": ["nonexistent"]})
        assert any("Unknown model" in e for e in errors)

    def test_valid_provider_restriction(self) -> None:
        errors = validate_rule("provider_restriction", {"provider": "openai"})
        assert errors == []

    def test_unknown_provider(self) -> None:
        errors = validate_rule("provider_restriction", {"provider": "google"})
        assert any("Unknown provider" in e for e in errors)

    def test_unknown_rule_type(self) -> None:
        errors = validate_rule("nonexistent_type", {})
        assert any("Unknown rule type" in e for e in errors)

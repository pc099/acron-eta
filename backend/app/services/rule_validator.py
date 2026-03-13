"""Validates routing constraint rules before persistence.

Checks model names, time ranges, fallback chain length, and step numbers.
Returns a list of validation errors — empty means valid.
"""

import logging
from typing import Optional

from app.services.routing import DEFAULT_MODELS

logger = logging.getLogger(__name__)

VALID_RULE_TYPES = frozenset({
    "step_based",
    "time_based",
    "fallback_chain",
    "cost_ceiling_per_1k",
    "model_allowlist",
    "provider_restriction",
})

KNOWN_PROVIDERS = frozenset({"openai", "anthropic"})


def validate_rule(
    rule_type: str,
    rule_config: dict,
    known_models: Optional[set[str]] = None,
) -> list[str]:
    """Validate a single routing constraint rule.

    Args:
        rule_type: The type of rule to validate.
        rule_config: The rule configuration payload.
        known_models: Set of known model IDs. Defaults to DEFAULT_MODELS keys.

    Returns:
        List of validation error strings. Empty list means valid.
    """
    models = known_models or set(DEFAULT_MODELS.keys())
    errors: list[str] = []

    if rule_type not in VALID_RULE_TYPES:
        errors.append(f"Unknown rule type: {rule_type}")
        return errors

    if rule_type == "step_based":
        errors.extend(_validate_step_based(rule_config, models))
    elif rule_type == "time_based":
        errors.extend(_validate_time_based(rule_config))
    elif rule_type == "fallback_chain":
        errors.extend(_validate_fallback_chain(rule_config, models))
    elif rule_type == "cost_ceiling_per_1k":
        errors.extend(_validate_cost_ceiling(rule_config))
    elif rule_type == "model_allowlist":
        errors.extend(_validate_model_allowlist(rule_config, models))
    elif rule_type == "provider_restriction":
        errors.extend(_validate_provider_restriction(rule_config))

    return errors


def _validate_step_based(config: dict, models: set[str]) -> list[str]:
    """Validate step_based rule config."""
    errors: list[str] = []
    rules = config.get("rules")
    if not rules or not isinstance(rules, list):
        errors.append("step_based requires a 'rules' list")
        return errors

    seen_steps: set[int] = set()
    for rule in rules:
        step = rule.get("step")
        model = rule.get("model")

        if not isinstance(step, int) or step < 1:
            errors.append(f"Step must be a positive integer, got: {step}")
            continue

        if step in seen_steps:
            errors.append(f"Duplicate step number: {step}")
        seen_steps.add(step)

        if model and model not in models:
            errors.append(f"Unknown model in step {step}: {model}")

    return errors


def _validate_time_based(config: dict) -> list[str]:
    """Validate time_based rule config."""
    errors: list[str] = []
    rules = config.get("rules")
    if not rules or not isinstance(rules, list):
        errors.append("time_based requires a 'rules' list")
        return errors

    covered_hours: set[int] = set()
    for rule in rules:
        hours_str = rule.get("hours", "")
        if "-" not in str(hours_str):
            errors.append(f"Time range must be in 'start-end' format, got: {hours_str}")
            continue

        parts = str(hours_str).split("-")
        if len(parts) != 2:
            errors.append(f"Invalid time range format: {hours_str}")
            continue

        try:
            start, end = int(parts[0]), int(parts[1])
        except ValueError:
            errors.append(f"Time range hours must be integers: {hours_str}")
            continue

        if not (0 <= start <= 23) or not (0 <= end <= 23):
            errors.append(f"Hours must be 0-23, got: {hours_str}")
            continue

        # Check for overlaps
        if start <= end:
            hours_in_range = set(range(start, end + 1))
        else:
            # Wraps midnight
            hours_in_range = set(range(start, 24)) | set(range(0, end + 1))

        overlap = covered_hours & hours_in_range
        if overlap:
            errors.append(f"Overlapping time range at hours: {sorted(overlap)}")
        covered_hours |= hours_in_range

    return errors


def _validate_fallback_chain(config: dict, models: set[str]) -> list[str]:
    """Validate fallback_chain rule config."""
    errors: list[str] = []
    chain = config.get("chain")
    if not chain or not isinstance(chain, list):
        errors.append("fallback_chain requires a 'chain' list")
        return errors

    if len(chain) < 2:
        errors.append("Fallback chain must have at least 2 models")

    for model_id in chain:
        if model_id not in models:
            errors.append(f"Unknown model in fallback chain: {model_id}")

    if len(chain) != len(set(chain)):
        errors.append("Fallback chain contains duplicate models")

    return errors


def _validate_cost_ceiling(config: dict) -> list[str]:
    """Validate cost_ceiling_per_1k rule config."""
    errors: list[str] = []
    value = config.get("value")
    if value is None:
        errors.append("cost_ceiling_per_1k requires a 'value' field")
        return errors

    try:
        fval = float(value)
        if fval <= 0:
            errors.append("Cost ceiling must be positive")
    except (TypeError, ValueError):
        errors.append(f"Cost ceiling must be a number, got: {value}")

    return errors


def _validate_model_allowlist(config: dict, models: set[str]) -> list[str]:
    """Validate model_allowlist rule config."""
    errors: list[str] = []
    model_list = config.get("models")
    if not model_list or not isinstance(model_list, list):
        errors.append("model_allowlist requires a 'models' list")
        return errors

    for model_id in model_list:
        if model_id not in models:
            errors.append(f"Unknown model in allowlist: {model_id}")

    return errors


def _validate_provider_restriction(config: dict) -> list[str]:
    """Validate provider_restriction rule config."""
    errors: list[str] = []
    provider = config.get("provider")
    if not provider:
        errors.append("provider_restriction requires a 'provider' field")
        return errors

    if provider not in KNOWN_PROVIDERS:
        errors.append(f"Unknown provider: {provider}. Known: {sorted(KNOWN_PROVIDERS)}")

    return errors

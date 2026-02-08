"""
Model profiles and definitions for Asahi inference optimizer.

Each model profile contains pricing, latency, quality, and token limit information
used by the router to make cost-optimal decisions.
"""

MODELS = {
    "gpt-4-turbo": {
        "provider": "openai",
        "api_key_env": "OPENAI_API_KEY",
        "cost_per_1k_input_tokens": 0.010,
        "cost_per_1k_output_tokens": 0.030,
        "avg_latency_ms": 200,
        "quality_score": 4.6,
        "max_input_tokens": 128000,
        "max_output_tokens": 4096,
        "description": "Most powerful, most expensive",
    },
    "claude-opus-4": {
        "provider": "anthropic",
        "api_key_env": "ANTHROPIC_API_KEY",
        "cost_per_1k_input_tokens": 0.015,
        "cost_per_1k_output_tokens": 0.045,
        "avg_latency_ms": 180,
        "quality_score": 4.5,
        "max_input_tokens": 200000,
        "max_output_tokens": 4096,
        "description": "High quality, moderate cost",
    },
    "claude-3-5-sonnet-20241022": {
        "provider": "anthropic",
        "api_key_env": "ANTHROPIC_API_KEY",
        "cost_per_1k_input_tokens": 0.003,
        "cost_per_1k_output_tokens": 0.015,
        "avg_latency_ms": 150,
        "quality_score": 4.1,
        "max_input_tokens": 200000,
        "max_output_tokens": 4096,
        "description": "Fast, cheap, reasonable quality",
    },
}


def estimate_tokens(text: str) -> int:
    """Quick token estimate. ~1.3 tokens per word."""
    if not text or not text.strip():
        return 0
    return max(1, int(len(text.split()) * 1.3))


def calculate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    """Calculate exact cost based on token counts and model pricing."""
    if model not in MODELS:
        raise ValueError(f"Unknown model: {model}")
    profile = MODELS[model]
    input_cost = (input_tokens / 1000) * profile["cost_per_1k_input_tokens"]
    output_cost = (output_tokens / 1000) * profile["cost_per_1k_output_tokens"]
    return round(input_cost + output_cost, 6)


def get_model_names() -> list[str]:
    """Return list of all available model names."""
    return list(MODELS.keys())


def get_model_profile(model: str) -> dict:
    """Return profile for a specific model, or raise ValueError."""
    if model not in MODELS:
        raise ValueError(f"Unknown model: {model}")
    return MODELS[model]

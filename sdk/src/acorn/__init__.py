"""Acorn Python SDK — LLM inference cost optimization.

Drop-in replacement for the OpenAI Python client with automatic
cost savings through smart routing, caching, and model selection.

Usage::

    from acorn import Acorn

    client = Acorn(api_key="asahi_live_...")
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hello"}],
    )
    print(response.choices[0].message.content)
    print(f"Saved: ${response.asahi.savings_usd}")
"""

from acorn._exceptions import (
    APIConnectionError,
    APIError,
    AcornError,
    AuthenticationError,
    BudgetExceededError,
    RateLimitError,
)
from acorn._version import __version__
from acorn.client import Acorn, AsyncAcorn

__all__ = [
    "Acorn",
    "AsyncAcorn",
    "AcornError",
    "AuthenticationError",
    "RateLimitError",
    "BudgetExceededError",
    "APIError",
    "APIConnectionError",
    "__version__",
]

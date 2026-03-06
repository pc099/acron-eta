"""ASAHIO Python SDK — LLM inference cost optimization.

Drop-in replacement for the OpenAI Python client with automatic
cost savings through smart routing, caching, and model selection.

Usage::

    from asahio import Asahio

    client = Asahio(api_key="asahi_live_...")
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hello"}],
    )
    print(response.choices[0].message.content)
    print(f"Saved: ${response.asahi.savings_usd}")
"""

from asahio._exceptions import (
    APIConnectionError,
    APIError,
    AsahioError,
    AuthenticationError,
    BudgetExceededError,
    RateLimitError,
)
from asahio._version import __version__
from asahio.client import Asahio, AsyncAsahio

__all__ = [
    "Asahio",
    "AsyncAsahio",
    "AsahioError",
    "AuthenticationError",
    "RateLimitError",
    "BudgetExceededError",
    "APIError",
    "APIConnectionError",
    "__version__",
]

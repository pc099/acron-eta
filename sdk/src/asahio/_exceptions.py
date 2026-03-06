"""ASAHIO SDK exceptions.

Maps HTTP status codes to typed exceptions so callers can handle
rate-limit, budget, and auth errors without inspecting raw responses.
"""

from __future__ import annotations

from typing import Any, Optional


class AsahioError(Exception):
    """Base exception for all ASAHIO SDK errors."""

    message: str
    status_code: Optional[int]
    body: Any

    def __init__(
        self,
        message: str = "An error occurred",
        *,
        status_code: Optional[int] = None,
        body: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.body = body


class AuthenticationError(AsahioError):
    """Raised when the API key is missing, invalid, or revoked (401/403)."""

    def __init__(self, body: Any = None) -> None:
        super().__init__(
            "Invalid or missing API key. Check your ASAHIO_API_KEY.",
            status_code=401,
            body=body,
        )


class RateLimitError(AsahioError):
    """Raised when the organisation has exceeded its monthly request limit (429)."""

    def __init__(self, body: Any = None) -> None:
        super().__init__(
            "Monthly request limit exceeded. Upgrade your plan for more requests.",
            status_code=429,
            body=body,
        )


class BudgetExceededError(AsahioError):
    """Raised when the organisation's monthly budget has been exhausted (402)."""

    def __init__(self, body: Any = None) -> None:
        super().__init__(
            "Monthly budget exceeded.",
            status_code=402,
            body=body,
        )


class APIError(AsahioError):
    """Raised for unexpected server-side errors (5xx)."""

    def __init__(self, status_code: int, body: Any = None) -> None:
        super().__init__(
            f"API returned status {status_code}",
            status_code=status_code,
            body=body,
        )


class APIConnectionError(AsahioError):
    """Raised when the SDK cannot reach the ASAHIO API."""

    def __init__(self, cause: Optional[Exception] = None) -> None:
        msg = "Could not connect to the ASAHIO API"
        if cause:
            msg = f"{msg}: {cause}"
        super().__init__(msg, status_code=None, body=None)
        self.__cause__ = cause

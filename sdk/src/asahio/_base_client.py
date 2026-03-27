"""Low-level HTTP client with retries, auth, and exception mapping.

Provides both sync (`BaseClient`) and async (`AsyncBaseClient`) variants
wrapping httpx.  All higher-level SDK classes delegate network calls here.
"""

from __future__ import annotations

import time
from typing import Any, Iterator, Optional

import httpx

from asahio._exceptions import (
    APIConnectionError,
    APIError,
    AsahioError,
    AuthenticationError,
    BudgetExceededError,
    ConflictError,
    RateLimitError,
)
from asahio._version import __version__

_USER_AGENT = f"asahio-python/{__version__}"
_DEFAULT_TIMEOUT = 120.0
_DEFAULT_MAX_RETRIES = 2
_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
_INITIAL_BACKOFF = 0.5  # seconds


def _map_error(response: httpx.Response) -> AsahioError:
    """Map an HTTP error response to the appropriate SDK exception."""
    body: Any = None
    try:
        body = response.json()
    except Exception:
        body = response.text

    status = response.status_code
    if status in (401, 403):
        return AuthenticationError(body)
    if status == 402:
        return BudgetExceededError(body)
    if status == 409:
        return ConflictError(body)
    if status == 429:
        return RateLimitError(body)
    return APIError(status, body)


class BaseClient:
    """Synchronous HTTP client with retry and exception handling."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout: float = _DEFAULT_TIMEOUT,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        org_slug: Optional[str] = None,
    ) -> None:
        headers: dict[str, str] = {
            "Authorization": f"Bearer {api_key}",
            "User-Agent": _USER_AGENT,
            "Content-Type": "application/json",
        }
        if org_slug:
            headers["X-Org-Slug"] = org_slug
        self._http = httpx.Client(
            base_url=base_url,
            headers=headers,
            timeout=timeout,
        )
        self._max_retries = max_retries

    # ── request helpers ──────────────────────────

    def post(self, path: str, *, json: dict[str, Any]) -> httpx.Response:
        """POST with retries on transient errors."""
        return self._request("POST", path, json=json)

    def post_stream(self, path: str, *, json: dict[str, Any]) -> httpx.Response:
        """POST returning a streaming response (caller must iterate)."""
        return self._request("POST", path, json=json, stream=True)

    def get(self, path: str, *, params: Optional[dict[str, Any]] = None) -> httpx.Response:
        """GET with optional query parameters."""
        return self._request("GET", path, params=params)

    def patch(self, path: str, *, json: dict[str, Any]) -> httpx.Response:
        """PATCH with retries on transient errors."""
        return self._request("PATCH", path, json=json)

    def put(self, path: str, *, json: dict[str, Any]) -> httpx.Response:
        """PUT with retries on transient errors."""
        return self._request("PUT", path, json=json)

    def delete(self, path: str) -> httpx.Response:
        """DELETE with retries on transient errors."""
        return self._request("DELETE", path)

    # ── internal ─────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
        stream: bool = False,
    ) -> httpx.Response:
        last_exc: Optional[Exception] = None
        for attempt in range(self._max_retries + 1):
            try:
                if stream:
                    req = self._http.build_request(method, path, json=json, params=params)
                    response = self._http.send(req, stream=True)
                else:
                    response = self._http.request(method, path, json=json, params=params)

                if response.status_code < 400:
                    return response

                # Non-retryable error
                if response.status_code not in _RETRY_STATUS_CODES:
                    raise _map_error(response)

                # Retryable — fall through to backoff
                last_exc = _map_error(response)

            except httpx.ConnectError as exc:
                last_exc = APIConnectionError(exc)
            except httpx.TimeoutException as exc:
                last_exc = APIConnectionError(exc)
            except AsahioError:
                raise

            # Exponential backoff
            if attempt < self._max_retries:
                time.sleep(_INITIAL_BACKOFF * (2 ** attempt))

        raise last_exc  # type: ignore[misc]

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> BaseClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class AsyncBaseClient:
    """Asynchronous HTTP client with retry and exception handling."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout: float = _DEFAULT_TIMEOUT,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        org_slug: Optional[str] = None,
    ) -> None:
        headers: dict[str, str] = {
            "Authorization": f"Bearer {api_key}",
            "User-Agent": _USER_AGENT,
            "Content-Type": "application/json",
        }
        if org_slug:
            headers["X-Org-Slug"] = org_slug
        self._http = httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            timeout=timeout,
        )
        self._max_retries = max_retries

    # ── request helpers ──────────────────────────

    async def post(self, path: str, *, json: dict[str, Any]) -> httpx.Response:
        return await self._request("POST", path, json=json)

    async def post_stream(self, path: str, *, json: dict[str, Any]) -> httpx.Response:
        return await self._request("POST", path, json=json, stream=True)

    async def get(self, path: str, *, params: Optional[dict[str, Any]] = None) -> httpx.Response:
        """GET with optional query parameters."""
        return await self._request("GET", path, params=params)

    async def patch(self, path: str, *, json: dict[str, Any]) -> httpx.Response:
        """PATCH with retries on transient errors."""
        return await self._request("PATCH", path, json=json)

    async def put(self, path: str, *, json: dict[str, Any]) -> httpx.Response:
        """PUT with retries on transient errors."""
        return await self._request("PUT", path, json=json)

    async def delete(self, path: str) -> httpx.Response:
        """DELETE with retries on transient errors."""
        return await self._request("DELETE", path)

    # ── internal ─────────────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
        stream: bool = False,
    ) -> httpx.Response:
        import anyio

        last_exc: Optional[Exception] = None
        for attempt in range(self._max_retries + 1):
            try:
                if stream:
                    req = self._http.build_request(method, path, json=json, params=params)
                    response = await self._http.send(req, stream=True)
                else:
                    response = await self._http.request(method, path, json=json, params=params)

                if response.status_code < 400:
                    return response

                if response.status_code not in _RETRY_STATUS_CODES:
                    raise _map_error(response)

                last_exc = _map_error(response)

            except httpx.ConnectError as exc:
                last_exc = APIConnectionError(exc)
            except httpx.TimeoutException as exc:
                last_exc = APIConnectionError(exc)
            except AsahioError:
                raise

            if attempt < self._max_retries:
                await anyio.sleep(_INITIAL_BACKOFF * (2 ** attempt))

        raise last_exc  # type: ignore[misc]

    async def close(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> AsyncBaseClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

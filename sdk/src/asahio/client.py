"""Public SDK clients — drop-in replacements for the OpenAI Python client.

Usage (sync):
    from asahio import Asahio

    client = Asahio(api_key="asahi_live_...")
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hello"}],
    )
    print(response.choices[0].message.content)
    print(f"Saved: {response.asahi.savings_pct}%")

Usage (async):
    from asahio import AsyncAsahio

    client = AsyncAsahio(api_key="asahi_live_...")
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hello"}],
    )
"""

from __future__ import annotations

import os
from typing import Any, Optional, Union, overload

from asahio._base_client import AsyncBaseClient, BaseClient
from asahio._exceptions import AsahioError
from asahio._streaming import AsyncStream, Stream
from asahio._version import __version__
from asahio.types.chat import ChatCompletion, ChatCompletionChunk

_DEFAULT_BASE_URL = "https://api.asahio.dev"


# ── Sync ─────────────────────────────────────────


class Completions:
    """Sync chat completions resource."""

    def __init__(self, client: BaseClient) -> None:
        self._client = client

    @overload
    def create(
        self,
        *,
        messages: list[dict[str, str]],
        model: str = "gpt-4o",
        stream: None = None,
        routing_mode: str = "AUTOPILOT",
        quality_preference: str = "high",
        latency_preference: str = "normal",
        **kwargs: Any,
    ) -> ChatCompletion: ...

    @overload
    def create(
        self,
        *,
        messages: list[dict[str, str]],
        model: str = "gpt-4o",
        stream: bool = ...,
        routing_mode: str = "AUTOPILOT",
        quality_preference: str = "high",
        latency_preference: str = "normal",
        **kwargs: Any,
    ) -> Union[ChatCompletion, Stream]: ...

    def create(
        self,
        *,
        messages: list[dict[str, str]],
        model: str = "gpt-4o",
        stream: Optional[bool] = None,
        routing_mode: str = "AUTOPILOT",
        quality_preference: str = "high",
        latency_preference: str = "normal",
        **kwargs: Any,
    ) -> Union[ChatCompletion, Stream]:
        """Create a chat completion — identical to ``openai.chat.completions.create``."""
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "routing_mode": routing_mode,
            "quality_preference": quality_preference,
            "latency_preference": latency_preference,
            **kwargs,
        }
        if stream:
            body["stream"] = True
            response = self._client.post_stream("/v1/chat/completions", json=body)
            return Stream(response)

        body["stream"] = False
        response = self._client.post("/v1/chat/completions", json=body)
        return ChatCompletion.from_dict(response.json())


class Chat:
    """Sync chat resource (mirrors ``openai.chat``)."""

    def __init__(self, client: BaseClient) -> None:
        self.completions = Completions(client)


class Asahio:
    """Synchronous ASAHIO client — drop-in replacement for ``openai.OpenAI``.

    Args:
        api_key: Your ASAHIO API key (``asahi_live_...``). Falls back to
            the ``ASAHIO_API_KEY`` environment variable.
        base_url: Override the default API endpoint.
        timeout: Request timeout in seconds.
        max_retries: Number of automatic retries on 429 / 5xx.
        org_slug: Organisation slug sent via ``X-Org-Slug`` header.
    """

    chat: Chat

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = 120.0,
        max_retries: int = 2,
        org_slug: Optional[str] = None,
    ) -> None:
        resolved_key = api_key or os.environ.get("ASAHIO_API_KEY")
        if not resolved_key:
            raise AsahioError(
                "No API key provided. Pass api_key= or set the ASAHIO_API_KEY env var."
            )
        self._client = BaseClient(
            base_url=base_url,
            api_key=resolved_key,
            timeout=timeout,
            max_retries=max_retries,
            org_slug=org_slug,
        )
        self.chat = Chat(self._client)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Asahio:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


# ── Async ────────────────────────────────────────


class AsyncCompletions:
    """Async chat completions resource."""

    def __init__(self, client: AsyncBaseClient) -> None:
        self._client = client

    async def create(
        self,
        *,
        messages: list[dict[str, str]],
        model: str = "gpt-4o",
        stream: Optional[bool] = None,
        routing_mode: str = "AUTOPILOT",
        quality_preference: str = "high",
        latency_preference: str = "normal",
        **kwargs: Any,
    ) -> Union[ChatCompletion, AsyncStream]:
        """Create a chat completion — async variant."""
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "routing_mode": routing_mode,
            "quality_preference": quality_preference,
            "latency_preference": latency_preference,
            **kwargs,
        }
        if stream:
            body["stream"] = True
            response = await self._client.post_stream(
                "/v1/chat/completions", json=body
            )
            return AsyncStream(response)

        body["stream"] = False
        response = await self._client.post("/v1/chat/completions", json=body)
        return ChatCompletion.from_dict(response.json())


class AsyncChat:
    """Async chat resource."""

    def __init__(self, client: AsyncBaseClient) -> None:
        self.completions = AsyncCompletions(client)


class AsyncAsahio:
    """Asynchronous ASAHIO client — drop-in replacement for ``openai.AsyncOpenAI``.

    Args:
        api_key: Your ASAHIO API key. Falls back to ``ASAHIO_API_KEY`` env var.
        base_url: Override the default API endpoint.
        timeout: Request timeout in seconds.
        max_retries: Number of automatic retries on 429 / 5xx.
        org_slug: Organisation slug sent via ``X-Org-Slug`` header.
    """

    chat: AsyncChat

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = 120.0,
        max_retries: int = 2,
        org_slug: Optional[str] = None,
    ) -> None:
        resolved_key = api_key or os.environ.get("ASAHIO_API_KEY")
        if not resolved_key:
            raise AsahioError(
                "No API key provided. Pass api_key= or set the ASAHIO_API_KEY env var."
            )
        self._client = AsyncBaseClient(
            base_url=base_url,
            api_key=resolved_key,
            timeout=timeout,
            max_retries=max_retries,
            org_slug=org_slug,
        )
        self.chat = AsyncChat(self._client)

    async def close(self) -> None:
        await self._client.close()

    async def __aenter__(self) -> AsyncAsahio:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

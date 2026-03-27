"""Public ASAHIO SDK clients."""

from __future__ import annotations

import os
from typing import Any, Optional, Union, overload

from asahio._base_client import AsyncBaseClient, BaseClient
from asahio._exceptions import AsahioError
from asahio._streaming import AsyncStream, Stream
from asahio.resources.aba import ABA, AsyncABA
from asahio.resources.agents import Agents, AsyncAgents
from asahio.resources.analytics import Analytics, AsyncAnalytics
from asahio.resources.billing import Billing, AsyncBilling
from asahio.resources.chains import AsyncChains, Chains
from asahio.resources.health import AsyncHealth, Health
from asahio.resources.interventions import AsyncInterventions, Interventions
from asahio.resources.models import AsyncModels, Models
from asahio.resources.ollama import AsyncOllama, Ollama
from asahio.resources.provider_keys import AsyncProviderKeys, ProviderKeys
from asahio.resources.routing import AsyncRouting, Routing
from asahio.resources.traces import AsyncTraces, Traces
from asahio.types.chat import ChatCompletion

_DEFAULT_BASE_URL = "https://api.asahio.in"


def _resolve_api_key(api_key: Optional[str]) -> str:
    resolved = (
        api_key
        or os.environ.get("ASAHIO_API_KEY")
        or os.environ.get("ASAHI_API_KEY")
        or os.environ.get("ACORN_API_KEY")
    )
    if not resolved:
        raise AsahioError(
            "No API key provided. Pass api_key= or set ASAHIO_API_KEY."
        )
    return resolved


def _build_body(
    *,
    messages: list[dict[str, str]],
    model: str,
    stream: bool,
    routing_mode: str,
    intervention_mode: str,
    quality_preference: str,
    latency_preference: str,
    agent_id: Optional[str],
    session_id: Optional[str],
    model_endpoint_id: Optional[str],
    chain_id: Optional[str],
    bypass_cache: bool,
    tools: Optional[list[dict]],
    tool_choice: Optional[Union[str, dict]],
    enable_web_search: bool,
    web_search_config: Optional[dict],
    mcp_servers: Optional[list[dict]],
    enable_computer_use: bool,
    computer_use_config: Optional[dict],
    extra: dict[str, Any],
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "routing_mode": routing_mode,
        "intervention_mode": intervention_mode,
        "quality_preference": quality_preference,
        "latency_preference": latency_preference,
        "bypass_cache": bypass_cache,
        **extra,
    }
    if agent_id is not None:
        body["agent_id"] = agent_id
    if session_id is not None:
        body["session_id"] = session_id
    if model_endpoint_id is not None:
        body["model_endpoint_id"] = model_endpoint_id
    if chain_id is not None:
        body["chain_id"] = chain_id
    if tools is not None:
        body["tools"] = tools
    if tool_choice is not None:
        body["tool_choice"] = tool_choice
    if enable_web_search:
        body["enable_web_search"] = True
        if web_search_config is not None:
            body["web_search_config"] = web_search_config
    if mcp_servers is not None:
        body["mcp_servers"] = mcp_servers
    if enable_computer_use:
        body["enable_computer_use"] = True
        if computer_use_config is not None:
            body["computer_use_config"] = computer_use_config
    return body


class Completions:
    def __init__(self, client: BaseClient) -> None:
        self._client = client

    @overload
    def create(
        self,
        *,
        messages: list[dict[str, str]],
        model: str = "gpt-4o",
        stream: None = None,
        routing_mode: str = "AUTO",
        intervention_mode: str = "OBSERVE",
        quality_preference: str = "high",
        latency_preference: str = "normal",
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        model_endpoint_id: Optional[str] = None,
        chain_id: Optional[str] = None,
        bypass_cache: bool = False,
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[Union[str, dict]] = None,
        enable_web_search: bool = False,
        web_search_config: Optional[dict] = None,
        mcp_servers: Optional[list[dict]] = None,
        enable_computer_use: bool = False,
        computer_use_config: Optional[dict] = None,
        **kwargs: Any,
    ) -> ChatCompletion: ...

    @overload
    def create(
        self,
        *,
        messages: list[dict[str, str]],
        model: str = "gpt-4o",
        stream: bool = ...,
        routing_mode: str = "AUTO",
        intervention_mode: str = "OBSERVE",
        quality_preference: str = "high",
        latency_preference: str = "normal",
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        model_endpoint_id: Optional[str] = None,
        chain_id: Optional[str] = None,
        bypass_cache: bool = False,
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[Union[str, dict]] = None,
        enable_web_search: bool = False,
        web_search_config: Optional[dict] = None,
        mcp_servers: Optional[list[dict]] = None,
        enable_computer_use: bool = False,
        computer_use_config: Optional[dict] = None,
        **kwargs: Any,
    ) -> Union[ChatCompletion, Stream]: ...

    def create(
        self,
        *,
        messages: list[dict[str, str]],
        model: str = "gpt-4o",
        stream: Optional[bool] = None,
        routing_mode: str = "AUTO",
        intervention_mode: str = "OBSERVE",
        quality_preference: str = "high",
        latency_preference: str = "normal",
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        model_endpoint_id: Optional[str] = None,
        chain_id: Optional[str] = None,
        bypass_cache: bool = False,
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[Union[str, dict]] = None,
        enable_web_search: bool = False,
        web_search_config: Optional[dict] = None,
        mcp_servers: Optional[list[dict]] = None,
        enable_computer_use: bool = False,
        computer_use_config: Optional[dict] = None,
        **kwargs: Any,
    ) -> Union[ChatCompletion, Stream]:
        body = _build_body(
            messages=messages,
            model=model,
            stream=bool(stream),
            routing_mode=routing_mode,
            intervention_mode=intervention_mode,
            quality_preference=quality_preference,
            latency_preference=latency_preference,
            agent_id=agent_id,
            session_id=session_id,
            model_endpoint_id=model_endpoint_id,
            chain_id=chain_id,
            bypass_cache=bypass_cache,
            tools=tools,
            tool_choice=tool_choice,
            enable_web_search=enable_web_search,
            web_search_config=web_search_config,
            mcp_servers=mcp_servers,
            enable_computer_use=enable_computer_use,
            computer_use_config=computer_use_config,
            extra=kwargs,
        )
        if stream:
            response = self._client.post_stream("/v1/chat/completions", json=body)
            return Stream(response)
        response = self._client.post("/v1/chat/completions", json=body)
        return ChatCompletion.from_dict(response.json())


class Chat:
    def __init__(self, client: BaseClient) -> None:
        self.completions = Completions(client)


class Asahio:
    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = 120.0,
        max_retries: int = 2,
        org_slug: Optional[str] = None,
    ) -> None:
        resolved_key = _resolve_api_key(api_key)
        self._client = BaseClient(
            base_url=base_url,
            api_key=resolved_key,
            timeout=timeout,
            max_retries=max_retries,
            org_slug=org_slug,
        )
        # Gateway
        self.chat = Chat(self._client)

        # Resources
        self.agents = Agents(self._client)
        self.aba = ABA(self._client)
        self.chains = Chains(self._client)
        self.provider_keys = ProviderKeys(self._client)
        self.ollama = Ollama(self._client)
        self.routing = Routing(self._client)
        self.traces = Traces(self._client)
        self.interventions = Interventions(self._client)
        self.analytics = Analytics(self._client)
        self.billing = Billing(self._client)
        self.models = Models(self._client)
        self.health = Health(self._client)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Asahio":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class AsyncCompletions:
    def __init__(self, client: AsyncBaseClient) -> None:
        self._client = client

    @overload
    async def create(
        self,
        *,
        messages: list[dict[str, str]],
        model: str = "gpt-4o",
        stream: None = None,
        routing_mode: str = "AUTO",
        intervention_mode: str = "OBSERVE",
        quality_preference: str = "high",
        latency_preference: str = "normal",
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        model_endpoint_id: Optional[str] = None,
        chain_id: Optional[str] = None,
        bypass_cache: bool = False,
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[Union[str, dict]] = None,
        enable_web_search: bool = False,
        web_search_config: Optional[dict] = None,
        mcp_servers: Optional[list[dict]] = None,
        enable_computer_use: bool = False,
        computer_use_config: Optional[dict] = None,
        **kwargs: Any,
    ) -> ChatCompletion: ...

    @overload
    async def create(
        self,
        *,
        messages: list[dict[str, str]],
        model: str = "gpt-4o",
        stream: bool = ...,
        routing_mode: str = "AUTO",
        intervention_mode: str = "OBSERVE",
        quality_preference: str = "high",
        latency_preference: str = "normal",
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        model_endpoint_id: Optional[str] = None,
        chain_id: Optional[str] = None,
        bypass_cache: bool = False,
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[Union[str, dict]] = None,
        enable_web_search: bool = False,
        web_search_config: Optional[dict] = None,
        mcp_servers: Optional[list[dict]] = None,
        enable_computer_use: bool = False,
        computer_use_config: Optional[dict] = None,
        **kwargs: Any,
    ) -> Union[ChatCompletion, AsyncStream]: ...

    async def create(
        self,
        *,
        messages: list[dict[str, str]],
        model: str = "gpt-4o",
        stream: Optional[bool] = None,
        routing_mode: str = "AUTO",
        intervention_mode: str = "OBSERVE",
        quality_preference: str = "high",
        latency_preference: str = "normal",
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        model_endpoint_id: Optional[str] = None,
        chain_id: Optional[str] = None,
        bypass_cache: bool = False,
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[Union[str, dict]] = None,
        enable_web_search: bool = False,
        web_search_config: Optional[dict] = None,
        mcp_servers: Optional[list[dict]] = None,
        enable_computer_use: bool = False,
        computer_use_config: Optional[dict] = None,
        **kwargs: Any,
    ) -> Union[ChatCompletion, AsyncStream]:
        body = _build_body(
            messages=messages,
            model=model,
            stream=bool(stream),
            routing_mode=routing_mode,
            intervention_mode=intervention_mode,
            quality_preference=quality_preference,
            latency_preference=latency_preference,
            agent_id=agent_id,
            session_id=session_id,
            model_endpoint_id=model_endpoint_id,
            chain_id=chain_id,
            bypass_cache=bypass_cache,
            tools=tools,
            tool_choice=tool_choice,
            enable_web_search=enable_web_search,
            web_search_config=web_search_config,
            mcp_servers=mcp_servers,
            enable_computer_use=enable_computer_use,
            computer_use_config=computer_use_config,
            extra=kwargs,
        )
        if stream:
            response = await self._client.post_stream("/v1/chat/completions", json=body)
            return AsyncStream(response)
        response = await self._client.post("/v1/chat/completions", json=body)
        return ChatCompletion.from_dict(response.json())


class AsyncChat:
    def __init__(self, client: AsyncBaseClient) -> None:
        self.completions = AsyncCompletions(client)


class AsyncAsahio:
    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = 120.0,
        max_retries: int = 2,
        org_slug: Optional[str] = None,
    ) -> None:
        resolved_key = _resolve_api_key(api_key)
        self._client = AsyncBaseClient(
            base_url=base_url,
            api_key=resolved_key,
            timeout=timeout,
            max_retries=max_retries,
            org_slug=org_slug,
        )
        # Gateway
        self.chat = AsyncChat(self._client)

        # Resources
        self.agents = AsyncAgents(self._client)
        self.aba = AsyncABA(self._client)
        self.chains = AsyncChains(self._client)
        self.provider_keys = AsyncProviderKeys(self._client)
        self.ollama = AsyncOllama(self._client)
        self.routing = AsyncRouting(self._client)
        self.traces = AsyncTraces(self._client)
        self.interventions = AsyncInterventions(self._client)
        self.analytics = AsyncAnalytics(self._client)
        self.billing = AsyncBilling(self._client)
        self.models = AsyncModels(self._client)
        self.health = AsyncHealth(self._client)

    async def close(self) -> None:
        await self._client.close()

    async def __aenter__(self) -> "AsyncAsahio":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()


Asahi = Asahio
AsyncAsahi = AsyncAsahio


Acorn = Asahio
AsyncAcorn = AsyncAsahio




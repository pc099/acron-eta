"""Chat completion types for the ASAHIO Python SDK."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AsahioMetadata:
    """Canonical ASAHIO metadata attached to every completion."""

    cache_hit: bool
    cache_tier: Optional[str]
    model_requested: Optional[str]
    model_used: str
    cost_without_asahio: float
    cost_with_asahio: float
    savings_usd: float
    savings_pct: float
    routing_reason: Optional[str] = None
    provider: Optional[str] = None
    routing_mode: Optional[str] = None
    intervention_mode: Optional[str] = None
    agent_id: Optional[str] = None
    agent_session_id: Optional[str] = None
    session_id: Optional[str] = None
    model_endpoint_id: Optional[str] = None
    routing_factors: dict = field(default_factory=dict)
    routing_confidence: Optional[float] = None
    policy_action: Optional[str] = None
    policy_reason: Optional[str] = None
    request_id: Optional[str] = None
    risk_score: Optional[float] = None
    risk_factors: dict = field(default_factory=dict)
    intervention_level: Optional[int] = None
    tools_requested: Optional[list[str]] = None
    tools_called: Optional[list[str]] = None
    cache_debug: Optional[dict] = None
    routing_debug: Optional[dict] = None
    intervention_debug: Optional[dict] = None

    @classmethod
    def from_dict(cls, data: dict) -> "AsahioMetadata":
        return cls(
            cache_hit=bool(data.get("cache_hit", False)),
            cache_tier=data.get("cache_tier"),
            model_requested=data.get("model_requested"),
            model_used=data.get("model_used", "unknown"),
            cost_without_asahio=float(data.get("cost_without_asahio", data.get("cost_without_asahi", 0.0))),
            cost_with_asahio=float(data.get("cost_with_asahio", data.get("cost_with_asahi", 0.0))),
            savings_usd=float(data.get("savings_usd", 0.0)),
            savings_pct=float(data.get("savings_pct", 0.0)),
            routing_reason=data.get("routing_reason"),
            provider=data.get("provider"),
            routing_mode=data.get("routing_mode"),
            intervention_mode=data.get("intervention_mode"),
            agent_id=data.get("agent_id"),
            agent_session_id=data.get("agent_session_id"),
            session_id=data.get("session_id"),
            model_endpoint_id=data.get("model_endpoint_id"),
            routing_factors=data.get("routing_factors") or {},
            routing_confidence=(float(data["routing_confidence"]) if data.get("routing_confidence") is not None else None),
            policy_action=data.get("policy_action"),
            policy_reason=data.get("policy_reason"),
            request_id=data.get("request_id"),
            risk_score=(float(data["risk_score"]) if data.get("risk_score") is not None else None),
            risk_factors=data.get("risk_factors") or {},
            intervention_level=data.get("intervention_level"),
            tools_requested=data.get("tools_requested"),
            tools_called=data.get("tools_called"),
            cache_debug=data.get("cache_debug"),
            routing_debug=data.get("routing_debug"),
            intervention_debug=data.get("intervention_debug"),
        )

    @property
    def cost_without_asahi(self) -> float:
        return self.cost_without_asahio

    @property
    def cost_with_asahi(self) -> float:
        return self.cost_with_asahio


AsahiMetadata = AsahioMetadata


@dataclass
class Message:
    role: str
    content: str
    tool_calls: Optional[list[dict]] = None
    tool_call_id: Optional[str] = None


@dataclass
class Choice:
    index: int
    message: Message
    finish_reason: str


@dataclass
class DeltaChoice:
    index: int
    delta: Message
    finish_reason: Optional[str] = None


@dataclass
class Usage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class ChatCompletion:
    id: str
    object: str
    model: str
    choices: list[Choice]
    usage: Usage
    asahio: AsahioMetadata

    @property
    def asahi(self) -> AsahioMetadata:
        return self.asahio

    @classmethod
    def from_dict(cls, data: dict) -> "ChatCompletion":
        choices = [
            Choice(
                index=choice["index"],
                message=Message(**choice["message"]),
                finish_reason=choice["finish_reason"],
            )
            for choice in data["choices"]
        ]
        usage = Usage(**data["usage"])
        metadata_payload = data.get("asahio") or data.get("asahi") or {}
        metadata = AsahioMetadata.from_dict(metadata_payload)
        return cls(
            id=data["id"],
            object=data["object"],
            model=data["model"],
            choices=choices,
            usage=usage,
            asahio=metadata,
        )


@dataclass
class ChatCompletionChunk:
    id: str
    object: str
    model: Optional[str] = None
    choices: list[DeltaChoice] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "ChatCompletionChunk":
        choices = []
        for choice in data.get("choices", []):
            delta_data = choice.get("delta") or {}
            delta = Message(
                role=delta_data.get("role", "assistant"),
                content=delta_data.get("content", ""),
                tool_calls=delta_data.get("tool_calls"),
                tool_call_id=delta_data.get("tool_call_id"),
            )
            choices.append(DeltaChoice(
                index=choice["index"],
                delta=delta,
                finish_reason=choice.get("finish_reason"),
            ))
        return cls(
            id=data["id"],
            object=data["object"],
            model=data.get("model"),
            choices=choices,
        )

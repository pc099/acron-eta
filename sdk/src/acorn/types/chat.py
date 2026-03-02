"""Chat completion types — mirrors the OpenAI response shape with an extra `asahi` field."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional


@dataclass
class AsahiMetadata:
    """ASAHI-specific metadata attached to every response."""

    cache_hit: bool
    cache_tier: Optional[str]  # "exact", "semantic", "intermediate", or None
    model_requested: Optional[str]
    model_used: str
    cost_without_asahi: float
    cost_with_asahi: float
    savings_usd: float
    savings_pct: float  # 0-100
    routing_reason: Optional[str] = None


@dataclass
class Message:
    role: str
    content: str


@dataclass
class Choice:
    index: int
    message: Message
    finish_reason: str


@dataclass
class DeltaChoice:
    """A single chunk delta in a streaming response."""

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
    """Full (non-streaming) chat completion response."""

    id: str
    object: str
    model: str
    choices: list[Choice]
    usage: Usage
    asahi: AsahiMetadata

    @classmethod
    def from_dict(cls, data: dict) -> ChatCompletion:
        """Build a ChatCompletion from a raw JSON dict."""
        choices = [
            Choice(
                index=c["index"],
                message=Message(**c["message"]),
                finish_reason=c["finish_reason"],
            )
            for c in data["choices"]
        ]
        usage = Usage(**data["usage"])
        asahi = AsahiMetadata(**data["asahi"])
        return cls(
            id=data["id"],
            object=data["object"],
            model=data["model"],
            choices=choices,
            usage=usage,
            asahi=asahi,
        )


@dataclass
class ChatCompletionChunk:
    """A single SSE chunk in a streaming response."""

    id: str
    object: str
    model: Optional[str] = None
    choices: list[DeltaChoice] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> ChatCompletionChunk:
        choices = [
            DeltaChoice(
                index=c["index"],
                delta=Message(**c.get("delta", {"role": "assistant", "content": ""})),
                finish_reason=c.get("finish_reason"),
            )
            for c in data.get("choices", [])
        ]
        return cls(
            id=data["id"],
            object=data["object"],
            model=data.get("model"),
            choices=choices,
        )

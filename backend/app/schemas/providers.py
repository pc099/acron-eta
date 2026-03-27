"""Pydantic request/response schemas for the providers API."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── BYOK Key Management ───────────────────────────────────────────────


VALID_PROVIDERS = frozenset({"openai", "anthropic", "google", "deepseek", "mistral"})


class ProviderKeyCreateRequest(BaseModel):
    provider: str = Field(..., description="Provider name (openai, anthropic, google, deepseek, mistral)")
    api_key: str = Field(..., min_length=1, description="The raw API key to store (encrypted at rest)")


class ProviderKeyResponse(BaseModel):
    id: str
    organisation_id: str
    provider: str
    key_hint: Optional[str] = None
    is_active: bool
    last_used_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


# ── Ollama Self-Hosted ─────────────────────────────────────────────────


class OllamaVerifyRequest(BaseModel):
    base_url: str = Field(..., description="Ollama server URL, e.g. http://10.0.0.5:11434")
    name: Optional[str] = Field(None, description="Friendly name for this Ollama instance")


class OllamaConfigResponse(BaseModel):
    id: str
    organisation_id: str
    name: Optional[str] = None
    base_url: str
    is_verified: bool
    available_models: list[str] = Field(default_factory=list)
    last_verified_at: Optional[datetime] = None
    is_active: bool
    created_at: Optional[datetime] = None


# ── Guided Chains ──────────────────────────────────────────────────────

VALID_TRIGGERS = frozenset({"rate_limit", "server_error", "timeout", "cost_ceiling", "no_key"})


class ChainSlotCreateRequest(BaseModel):
    provider: str
    model: str
    priority: int = Field(..., ge=1, le=3, description="Slot priority (1=primary, 2=fallback, 3=last resort)")
    max_latency_ms: Optional[int] = None
    max_cost_per_1k_tokens: Optional[float] = None


class ChainCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    fallback_triggers: list[str] = Field(
        default=["rate_limit", "server_error", "timeout"],
        description="Trigger types that cause fallback to the next slot",
    )
    is_default: bool = False
    slots: list[ChainSlotCreateRequest] = Field(..., min_length=1, max_length=3)


class ChainSlotResponse(BaseModel):
    id: str
    chain_id: str
    provider: str
    model: str
    priority: int
    max_latency_ms: Optional[int] = None
    max_cost_per_1k_tokens: Optional[float] = None


class ChainResponse(BaseModel):
    id: str
    organisation_id: str
    name: str
    fallback_triggers: list[str]
    is_default: bool
    is_active: bool
    slots: list[ChainSlotResponse] = Field(default_factory=list)
    created_at: Optional[datetime] = None


class ChainTestSlotResult(BaseModel):
    position: int
    provider: str
    model: str
    key_available: bool
    error: Optional[str] = None


class ChainTestResponse(BaseModel):
    chain_id: str
    ready: bool
    slots: list[ChainTestSlotResult]

"""Trace and session types for the ASAHIO Python SDK."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Trace:
    """A call trace record."""

    id: str
    organisation_id: str
    agent_id: Optional[str]
    agent_session_id: Optional[str]
    request_id: Optional[str]
    model_requested: Optional[str]
    model_used: Optional[str]
    provider: Optional[str]
    routing_mode: Optional[str]
    intervention_mode: Optional[str]
    policy_action: Optional[str]
    policy_reason: Optional[str]
    cache_hit: bool
    cache_tier: Optional[str]
    input_tokens: int
    output_tokens: int
    latency_ms: Optional[int]
    risk_score: Optional[float]
    intervention_level: Optional[int]
    trace_metadata: dict
    created_at: str

    @classmethod
    def from_dict(cls, data: dict) -> "Trace":
        return cls(
            id=data["id"],
            organisation_id=data["organisation_id"],
            agent_id=data.get("agent_id"),
            agent_session_id=data.get("agent_session_id"),
            request_id=data.get("request_id"),
            model_requested=data.get("model_requested"),
            model_used=data.get("model_used"),
            provider=data.get("provider"),
            routing_mode=data.get("routing_mode"),
            intervention_mode=data.get("intervention_mode"),
            policy_action=data.get("policy_action"),
            policy_reason=data.get("policy_reason"),
            cache_hit=data.get("cache_hit", False),
            cache_tier=data.get("cache_tier"),
            input_tokens=data.get("input_tokens", 0),
            output_tokens=data.get("output_tokens", 0),
            latency_ms=data.get("latency_ms"),
            risk_score=data.get("risk_score"),
            intervention_level=data.get("intervention_level"),
            trace_metadata=data.get("trace_metadata") or {},
            created_at=data["created_at"],
        )


@dataclass
class Session:
    """An agent session."""

    id: str
    organisation_id: str
    agent_id: str
    external_session_id: str
    started_at: str
    last_seen_at: Optional[str] = None
    trace_count: int = 0
    stats: Optional[dict] = None

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        return cls(
            id=data["id"],
            organisation_id=data["organisation_id"],
            agent_id=data["agent_id"],
            external_session_id=data["external_session_id"],
            started_at=data["started_at"],
            last_seen_at=data.get("last_seen_at"),
            trace_count=data.get("trace_count", 0),
            stats=data.get("stats"),
        )

    @property
    def total_calls(self) -> int:
        """Alias for trace_count for backward compatibility."""
        return self.trace_count


@dataclass
class SessionStep:
    """A step in a session graph."""

    step_number: int
    call_trace_id: str
    model_used: str
    cache_hit: bool
    latency_ms: Optional[int]
    created_at: str
    depends_on: list[int]

    @classmethod
    def from_dict(cls, data: dict) -> "SessionStep":
        return cls(
            step_number=data["step_number"],
            call_trace_id=data["call_trace_id"],
            model_used=data["model_used"],
            cache_hit=data.get("cache_hit", False),
            latency_ms=data.get("latency_ms"),
            created_at=data["created_at"],
            depends_on=data.get("depends_on") or [],
        )


@dataclass
class SessionGraph:
    """Session execution graph."""

    session_id: str
    step_count: int
    steps: list[SessionStep]

    @classmethod
    def from_dict(cls, data: dict) -> "SessionGraph":
        return cls(
            session_id=data["session_id"],
            step_count=data["step_count"],
            steps=[SessionStep.from_dict(s) for s in data.get("steps", [])],
        )

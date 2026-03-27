"""Agent-related types for the ASAHIO Python SDK."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Agent:
    """An ASAHIO agent configuration."""

    id: str
    name: str
    slug: str
    organisation_id: str
    description: Optional[str]
    routing_mode: str
    intervention_mode: str
    model_endpoint_id: Optional[str]
    is_active: bool
    metadata: dict
    risk_threshold_overrides: Optional[dict]
    mode_entered_at: Optional[str]
    autonomous_authorized_at: Optional[str]
    autonomous_authorized_by: Optional[str]
    blueprint_id: Optional[str]
    created_at: str
    updated_at: Optional[str]

    @classmethod
    def from_dict(cls, data: dict) -> "Agent":
        return cls(
            id=data["id"],
            name=data["name"],
            slug=data["slug"],
            organisation_id=data["organisation_id"],
            description=data.get("description"),
            routing_mode=data.get("routing_mode", "AUTO"),
            intervention_mode=data.get("intervention_mode", "OBSERVE"),
            model_endpoint_id=data.get("model_endpoint_id"),
            is_active=data.get("is_active", True),
            metadata=data.get("metadata") or {},
            risk_threshold_overrides=data.get("risk_threshold_overrides"),
            mode_entered_at=data.get("mode_entered_at"),
            autonomous_authorized_at=data.get("autonomous_authorized_at"),
            autonomous_authorized_by=data.get("autonomous_authorized_by"),
            blueprint_id=data.get("blueprint_id"),
            created_at=data["created_at"],
            updated_at=data.get("updated_at"),
        )


@dataclass
class AgentStats:
    """Statistics for an agent."""

    agent_id: str
    total_calls: int
    cache_hits: int
    cache_hit_rate: float
    avg_latency_ms: Optional[float]
    total_input_tokens: int
    total_output_tokens: int
    total_sessions: int

    @classmethod
    def from_dict(cls, data: dict) -> "AgentStats":
        return cls(
            agent_id=data["agent_id"],
            total_calls=data["total_calls"],
            cache_hits=data["cache_hits"],
            cache_hit_rate=data["cache_hit_rate"],
            avg_latency_ms=data.get("avg_latency_ms"),
            total_input_tokens=data["total_input_tokens"],
            total_output_tokens=data["total_output_tokens"],
            total_sessions=data["total_sessions"],
        )


@dataclass
class ModeEligibility:
    """Mode transition eligibility status."""

    agent_id: str
    current_mode: str
    eligible: bool
    suggested_mode: Optional[str]
    reason: str
    evidence: dict

    @classmethod
    def from_dict(cls, data: dict) -> "ModeEligibility":
        return cls(
            agent_id=data["agent_id"],
            current_mode=data["current_mode"],
            eligible=data["eligible"],
            suggested_mode=data.get("suggested_mode"),
            reason=data["reason"],
            evidence=data.get("evidence") or {},
        )


@dataclass
class ModeTransition:
    """Result of a mode transition request."""

    agent_id: str
    previous_mode: str
    new_mode: str
    transition_reason: str

    @classmethod
    def from_dict(cls, data: dict) -> "ModeTransition":
        return cls(
            agent_id=data["agent_id"],
            previous_mode=data["previous_mode"],
            new_mode=data["new_mode"],
            transition_reason=data["transition_reason"],
        )


@dataclass
class ModeHistoryEntry:
    """A single mode transition history entry."""

    id: str
    previous_mode: str
    new_mode: str
    trigger: str
    baseline_confidence: Optional[float]
    evidence: dict
    operator_user_id: Optional[str]
    created_at: str
    agent_id: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "ModeHistoryEntry":
        return cls(
            id=data["id"],
            agent_id=data.get("agent_id"),
            previous_mode=data["previous_mode"],
            new_mode=data["new_mode"],
            trigger=data["trigger"],
            baseline_confidence=data.get("baseline_confidence"),
            evidence=data.get("evidence") or {},
            operator_user_id=data.get("operator_user_id"),
            created_at=data["created_at"],
        )


@dataclass
class AgentSession:
    """An agent session."""

    id: str
    agent_id: str
    external_session_id: str
    started_at: str
    last_seen_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "AgentSession":
        return cls(
            id=data["id"],
            agent_id=data["agent_id"],
            external_session_id=data["external_session_id"],
            started_at=data["started_at"],
            last_seen_at=data.get("last_seen_at"),
        )

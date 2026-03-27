"""ABA (Agent Behavioral Analytics) types for the ASAHIO Python SDK."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Fingerprint:
    """Agent behavioral fingerprint."""

    agent_id: str
    organisation_id: str
    total_observations: int
    avg_complexity: float
    avg_context_length: float
    hallucination_rate: float
    model_distribution: dict
    cache_hit_rate: float
    baseline_confidence: float
    tool_usage_distribution: Optional[dict]
    tool_success_rates: Optional[dict]
    tool_risk_correlation: Optional[dict]
    preferred_model_by_tool: Optional[dict]
    last_updated_at: str
    created_at: str

    @classmethod
    def from_dict(cls, data: dict) -> "Fingerprint":
        return cls(
            agent_id=str(data["agent_id"]),
            organisation_id=str(data["organisation_id"]),
            total_observations=data["total_observations"],
            avg_complexity=data["avg_complexity"],
            avg_context_length=data["avg_context_length"],
            hallucination_rate=data["hallucination_rate"],
            model_distribution=data.get("model_distribution") or {},
            cache_hit_rate=data["cache_hit_rate"],
            baseline_confidence=data["baseline_confidence"],
            tool_usage_distribution=data.get("tool_usage_distribution"),
            tool_success_rates=data.get("tool_success_rates"),
            tool_risk_correlation=data.get("tool_risk_correlation"),
            preferred_model_by_tool=data.get("preferred_model_by_tool"),
            last_updated_at=str(data["last_updated_at"]),
            created_at=str(data["created_at"]),
        )


@dataclass
class StructuralRecord:
    """A structural analysis record."""

    id: str
    agent_id: str
    call_trace_id: Optional[str]
    query_complexity_score: float
    agent_type_classification: str
    output_type_classification: str
    token_count: int
    latency_ms: Optional[int]
    model_used: str
    cache_hit: bool
    hallucination_detected: bool
    created_at: str
    organisation_id: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "StructuralRecord":
        return cls(
            id=str(data["id"]),
            agent_id=str(data["agent_id"]),
            organisation_id=str(data["organisation_id"]) if data.get("organisation_id") else None,
            call_trace_id=str(data["call_trace_id"]) if data.get("call_trace_id") else None,
            query_complexity_score=data["query_complexity_score"],
            agent_type_classification=data["agent_type_classification"],
            output_type_classification=data["output_type_classification"],
            token_count=data["token_count"],
            latency_ms=data.get("latency_ms"),
            model_used=data["model_used"],
            cache_hit=data["cache_hit"],
            hallucination_detected=data["hallucination_detected"],
            created_at=str(data["created_at"]),
        )


@dataclass
class RiskPrior:
    """Global risk prior from Model C."""

    risk_score: float
    observation_count: int
    confidence: float
    recommended_model: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "RiskPrior":
        return cls(
            risk_score=data["risk_score"],
            observation_count=data.get("observation_count", data.get("sample_size", 0)),
            confidence=data.get("confidence", 0.0),
            recommended_model=data.get("recommended_model"),
        )


@dataclass
class AnomalyItem:
    """An anomaly detection result."""

    agent_id: str
    anomaly_type: str
    severity: str
    current_value: float
    baseline_value: float
    deviation_pct: float
    detected_at: str
    metadata: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "AnomalyItem":
        return cls(
            agent_id=str(data["agent_id"]),
            anomaly_type=data["anomaly_type"],
            severity=data["severity"],
            current_value=data.get("current_value", 0.0),
            baseline_value=data.get("baseline_value", 0.0),
            deviation_pct=data.get("deviation_pct", 0.0),
            detected_at=str(data["detected_at"]),
            metadata=data.get("metadata") or {},
        )


@dataclass
class ColdStartStatus:
    """Cold start status for an agent."""

    agent_id: str
    is_cold_start: bool
    total_observations: int
    cold_start_threshold: int
    progress_pct: float
    bootstrap_source: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "ColdStartStatus":
        return cls(
            agent_id=str(data["agent_id"]),
            is_cold_start=data["is_cold_start"],
            total_observations=data["total_observations"],
            cold_start_threshold=data.get("cold_start_threshold", 10),
            progress_pct=data.get("progress_pct", 0.0),
            bootstrap_source=data.get("bootstrap_source"),
        )


@dataclass
class OrgOverview:
    """Organization-wide ABA overview."""

    total_agents: int
    total_observations: int
    avg_baseline_confidence: float
    avg_hallucination_rate: float
    avg_cache_hit_rate: float
    cold_start_agents: int
    anomaly_count: int
    top_anomalies: list[AnomalyItem]
    hallucination_distribution: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "OrgOverview":
        return cls(
            total_agents=data["total_agents"],
            total_observations=data["total_observations"],
            avg_baseline_confidence=data.get("avg_baseline_confidence", 0.0),
            avg_hallucination_rate=data.get("avg_hallucination_rate", 0.0),
            avg_cache_hit_rate=data.get("avg_cache_hit_rate", 0.0),
            cold_start_agents=data.get("cold_start_agents", 0),
            anomaly_count=data.get("anomaly_count", 0),
            top_anomalies=[AnomalyItem.from_dict(a) for a in data.get("top_anomalies", [])],
            hallucination_distribution=data.get("hallucination_distribution") or {},
        )

"""Analytics types for the ASAHIO Python SDK."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Overview:
    """Analytics overview KPIs."""

    period: str
    total_requests: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost_without_asahi: float
    total_cost_with_asahi: float
    total_savings_usd: float
    average_savings_pct: float
    cache_hit_rate: float
    cache_hits: dict
    avg_latency_ms: float
    p99_latency_ms: Optional[int] = None
    savings_delta_pct: float = 0.0
    requests_delta_pct: float = 0.0

    @classmethod
    def from_dict(cls, data: dict) -> "Overview":
        return cls(
            period=data.get("period", "30d"),
            total_requests=data.get("total_requests", 0),
            total_input_tokens=data.get("total_input_tokens", 0),
            total_output_tokens=data.get("total_output_tokens", 0),
            total_cost_without_asahi=data.get("total_cost_without_asahi", 0.0),
            total_cost_with_asahi=data.get("total_cost_with_asahi", 0.0),
            total_savings_usd=data.get("total_savings_usd", 0.0),
            average_savings_pct=data.get("average_savings_pct", 0.0),
            cache_hit_rate=data.get("cache_hit_rate", 0.0),
            cache_hits=data.get("cache_hits") or {},
            avg_latency_ms=data.get("avg_latency_ms", 0.0),
            p99_latency_ms=data.get("p99_latency_ms"),
            savings_delta_pct=data.get("savings_delta_pct", 0.0),
            requests_delta_pct=data.get("requests_delta_pct", 0.0),
        )

    # Convenience aliases
    @property
    def total_cost(self) -> float:
        return self.total_cost_with_asahi

    @property
    def total_savings(self) -> float:
        return self.total_savings_usd


@dataclass
class SavingsEntry:
    """Time-series savings entry."""

    timestamp: str
    cost_without_asahi: float
    cost_with_asahi: float
    savings_usd: float
    requests: int

    @classmethod
    def from_dict(cls, data: dict) -> "SavingsEntry":
        return cls(
            timestamp=data["timestamp"],
            cost_without_asahi=data["cost_without_asahi"],
            cost_with_asahi=data["cost_with_asahi"],
            savings_usd=data["savings_usd"],
            requests=data["requests"],
        )


@dataclass
class ModelBreakdown:
    """Model usage breakdown."""

    model: str
    requests: int
    total_cost: float
    total_savings: float

    @classmethod
    def from_dict(cls, data: dict) -> "ModelBreakdown":
        return cls(
            model=data["model"],
            requests=data["requests"],
            total_cost=data["total_cost"],
            total_savings=data.get("total_savings", 0.0),
        )


@dataclass
class CachePerformance:
    """Cache performance metrics."""

    total_requests: int
    cache_hit_rate: float
    tiers: dict

    @classmethod
    def from_dict(cls, data: dict) -> "CachePerformance":
        return cls(
            total_requests=data["total_requests"],
            cache_hit_rate=data["cache_hit_rate"],
            tiers=data.get("tiers") or {},
        )

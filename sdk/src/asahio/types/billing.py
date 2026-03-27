"""Billing types for the ASAHIO Python SDK."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class BillingPlan:
    """A billing plan."""

    id: str
    name: str
    price_monthly: float
    request_limit: Optional[int]
    token_limit: Optional[int]
    features: list[str]

    @classmethod
    def from_dict(cls, data: dict) -> "BillingPlan":
        return cls(
            id=data["id"],
            name=data["name"],
            price_monthly=data["price_monthly"],
            request_limit=data.get("request_limit"),
            token_limit=data.get("token_limit"),
            features=data.get("features") or [],
        )


@dataclass
class Subscription:
    """Organization subscription status."""

    plan: str
    subscription_status: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    current_period_start: Optional[str] = None
    current_period_end: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "Subscription":
        return cls(
            plan=data.get("plan", data.get("plan_id", "unknown")),
            subscription_status=data.get("subscription_status", data.get("status")),
            stripe_customer_id=data.get("stripe_customer_id"),
            stripe_subscription_id=data.get("stripe_subscription_id"),
            current_period_start=data.get("current_period_start"),
            current_period_end=data.get("current_period_end"),
        )


@dataclass
class BillingUsage:
    """Current billing period usage."""

    month: str
    requests_used: int
    tokens_used: int
    spend_usd: float
    request_limit: Optional[int]
    token_limit: Optional[int]
    request_usage_pct: Optional[float]
    token_usage_pct: Optional[float]

    @classmethod
    def from_dict(cls, data: dict) -> "BillingUsage":
        return cls(
            month=data["month"],
            requests_used=data["requests_used"],
            tokens_used=data["tokens_used"],
            spend_usd=data["spend_usd"],
            request_limit=data.get("request_limit"),
            token_limit=data.get("token_limit"),
            request_usage_pct=data.get("request_usage_pct"),
            token_usage_pct=data.get("token_usage_pct"),
        )

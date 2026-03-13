"""Stripe billing helpers for ASAHIO."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import BillingAccount, BillingStatus, Organisation, PlanTier

logger = logging.getLogger(__name__)

try:
    import stripe
except Exception:  # pragma: no cover - optional at test time
    stripe = None  # type: ignore[assignment]

PLANS: dict[str, dict[str, Any]] = {
    "free": {
        "name": "Free",
        "monthly_request_limit": 10_000,
        "monthly_token_limit": 1_000_000,
        "monthly_budget_usd": 0,
        "price_monthly_usd": 0,
        "features": ["Gateway", "Cache", "Dashboard", "Basic analytics"],
    },
    "pro": {
        "name": "Pro",
        "monthly_request_limit": 250_000,
        "monthly_token_limit": 20_000_000,
        "monthly_budget_usd": 499,
        "price_monthly_usd": 499,
        "features": [
            "All Free features",
            "Billing insights",
            "Agent registry",
            "Routing decision logs",
        ],
    },
    "enterprise": {
        "name": "Enterprise",
        "monthly_request_limit": -1,
        "monthly_token_limit": -1,
        "monthly_budget_usd": None,
        "price_monthly_usd": None,
        "features": [
            "Unlimited scale",
            "Compliance tier routing",
            "BYOM registry",
            "Priority support",
        ],
    },
}


def _init_stripe() -> bool:
    settings = get_settings()
    if not stripe or not settings.stripe_secret_key:
        return False
    stripe.api_key = settings.stripe_secret_key
    return True


def _event_get(event: Any, key: str, default: Any = None) -> Any:
    if isinstance(event, dict):
        return event.get(key, default)
    return getattr(event, key, default)


def _metadata_get(obj: Any, key: str) -> Any:
    metadata = _event_get(obj, "metadata", {}) or {}
    if isinstance(metadata, dict):
        return metadata.get(key)
    getter = getattr(metadata, "get", None)
    if callable(getter):
        return getter(key)
    return None


async def ensure_billing_account(db: AsyncSession, org: Organisation) -> BillingAccount:
    result = await db.execute(
        select(BillingAccount).where(BillingAccount.organisation_id == org.id)
    )
    account = result.scalar_one_or_none()
    if account:
        return account

    account = BillingAccount(
        organisation_id=org.id,
        plan=org.plan,
        status=BillingStatus.TRIALING if org.plan == PlanTier.FREE else BillingStatus.ACTIVE,
        stripe_meter_name="asahio_tokens",
    )
    db.add(account)
    await db.flush()
    return account


async def get_billing_summary(db: AsyncSession, org: Organisation) -> dict[str, Any]:
    account = await ensure_billing_account(db, org)
    plan_data = PLANS[account.plan.value]
    return {
        "plan": account.plan.value,
        "plan_name": plan_data["name"],
        "status": account.status.value,
        "stripe_customer_id": org.stripe_customer_id,
        "stripe_subscription_id": org.stripe_subscription_id,
        "stripe_price_id": account.stripe_price_id,
        "billing_email": account.billing_email,
        "current_period_start": account.current_period_start.isoformat() if account.current_period_start else None,
        "current_period_end": account.current_period_end.isoformat() if account.current_period_end else None,
        "monthly_request_limit": plan_data["monthly_request_limit"],
        "monthly_token_limit": plan_data["monthly_token_limit"],
        "monthly_budget_usd": plan_data["monthly_budget_usd"],
        "price_monthly_usd": plan_data["price_monthly_usd"],
        "features": plan_data["features"],
        "meter_name": account.stripe_meter_name,
        "stripe_enabled": bool(get_settings().stripe_secret_key and stripe),
    }


async def create_checkout_session(
    db: AsyncSession,
    org: Organisation,
    plan: str,
    success_url: str,
    cancel_url: str,
) -> dict[str, Any]:
    account = await ensure_billing_account(db, org)
    normalized = plan.lower()
    if normalized not in PLANS or normalized == "free":
        raise ValueError("Unsupported checkout plan")

    if not _init_stripe():
        return {
            "checkout_url": f"{success_url}?mock_billing=1&plan={normalized}",
            "mode": "mock",
        }

    if not org.stripe_customer_id:
        customer = stripe.Customer.create(name=org.name, metadata={"org_id": str(org.id)})
        org.stripe_customer_id = customer.id

    settings = get_settings()
    price_id = settings.stripe_pro_price_id if normalized == "pro" else None
    if not price_id:
        return {
            "checkout_url": f"{success_url}?mock_billing=1&plan={normalized}",
            "mode": "mock",
        }

    session = stripe.checkout.Session.create(
        customer=org.stripe_customer_id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"org_id": str(org.id), "plan": normalized},
    )
    account.stripe_price_id = price_id
    await db.flush()
    return {"checkout_url": session.url, "mode": "stripe"}


async def create_portal_session(
    db: AsyncSession, org: Organisation, return_url: str
) -> dict[str, Any]:
    await ensure_billing_account(db, org)
    if not _init_stripe() or not org.stripe_customer_id:
        return {"portal_url": return_url, "mode": "mock"}

    session = stripe.billing_portal.Session.create(
        customer=org.stripe_customer_id,
        return_url=return_url,
    )
    return {"portal_url": session.url, "mode": "stripe"}


async def list_invoices(org: Organisation) -> list[dict[str, Any]]:
    if not _init_stripe() or not org.stripe_customer_id:
        return []

    invoices = stripe.Invoice.list(customer=org.stripe_customer_id, limit=20)
    rows: list[dict[str, Any]] = []
    for invoice in invoices.auto_paging_iter():
        rows.append(
            {
                "id": invoice.id,
                "amount_paid": (invoice.amount_paid or 0) / 100,
                "amount_due": (invoice.amount_due or 0) / 100,
                "currency": invoice.currency,
                "status": invoice.status,
                "hosted_invoice_url": invoice.hosted_invoice_url,
                "created_at": datetime.fromtimestamp(invoice.created, tz=timezone.utc).isoformat(),
            }
        )
    return rows


async def record_stripe_usage(
    org: Organisation,
    token_count: int,
    event_id: str,
    max_retries: int = 3,
) -> None:
    """Record token usage as a Stripe billing meter event.

    Retries with exponential backoff on failure. After all retries
    are exhausted the error is logged but never propagated.
    """
    if token_count <= 0 or not _init_stripe() or not org.stripe_customer_id:
        return

    for attempt in range(1, max_retries + 1):
        try:
            stripe.billing.MeterEvent.create(
                event_name="asahio_tokens",
                payload={
                    "value": str(token_count),
                    "stripe_customer_id": org.stripe_customer_id,
                },
                identifier=event_id,
            )
            return  # success
        except Exception as exc:
            if attempt < max_retries:
                logger.warning(
                    "Stripe meter event attempt %d/%d failed for org %s: %s",
                    attempt,
                    max_retries,
                    org.id,
                    exc,
                )
                await asyncio.sleep(2 ** (attempt - 1))  # 1s, 2s
            else:
                logger.error(
                    "Stripe meter event failed after %d attempts for org %s, "
                    "event_id=%s, tokens=%d: %s",
                    max_retries,
                    org.id,
                    event_id,
                    token_count,
                    exc,
                    extra={
                        "org_id": str(org.id),
                        "event_id": event_id,
                        "tokens": token_count,
                    },
                )


async def handle_webhook(
    db: AsyncSession,
    payload: bytes,
    signature: Optional[str],
    redis: Any = None,
) -> dict[str, Any]:
    settings = get_settings()

    if _init_stripe() and settings.stripe_webhook_secret and signature:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=signature,
            secret=settings.stripe_webhook_secret,
        )
    else:
        event = json.loads(payload.decode("utf-8"))

    event_id = _event_get(event, "id")
    redis_key = None
    if redis and event_id:
        redis_key = f"asahio:stripe:webhook:{event_id}"
        try:
            if await redis.get(redis_key):
                return {"received": True, "duplicate": True}
        except Exception:
            redis_key = None

    event_type = _event_get(event, "type")
    data = _event_get(event, "data", {}) or {}
    data_object = data.get("object") if isinstance(data, dict) else getattr(data, "object", None)
    if not data_object:
        return {"received": True, "ignored": True}

    org_id_raw = _metadata_get(data_object, "org_id")
    if not org_id_raw:
        return {"received": True, "ignored": True}

    try:
        org_id = uuid.UUID(str(org_id_raw))
    except ValueError:
        return {"received": True, "ignored": True}

    org = await db.get(Organisation, org_id)
    if not org:
        return {"received": True, "ignored": True}

    account = await ensure_billing_account(db, org)

    if event_type in {"checkout.session.completed", "customer.subscription.created", "customer.subscription.updated"}:
        plan = _metadata_get(data_object, "plan")
        if plan in PLANS:
            account.plan = PlanTier(plan)
            account.status = BillingStatus.ACTIVE
            org.plan = PlanTier(plan)
        org.stripe_customer_id = _event_get(data_object, "customer", org.stripe_customer_id)
        org.stripe_subscription_id = _event_get(data_object, "subscription", org.stripe_subscription_id)
    elif event_type == "customer.subscription.deleted":
        account.status = BillingStatus.CANCELED
        account.plan = PlanTier.FREE
        org.plan = PlanTier.FREE
    elif event_type == "invoice.payment_failed":
        account.status = BillingStatus.PAST_DUE
    elif event_type == "invoice.paid" and account.status != BillingStatus.CANCELED:
        account.status = BillingStatus.ACTIVE

    await db.flush()
    if redis and redis_key:
        try:
            await redis.set(redis_key, "1", ex=86400)
        except Exception:
            pass
    return {"received": True, "type": event_type}


# -- Usage threshold alerts ------------------------------------------------

from dataclasses import dataclass


@dataclass
class UsageAlert:
    """An alert when usage crosses a threshold."""

    threshold_pct: int
    resource: str  # "requests" or "tokens"
    current: int
    limit: int


def check_usage_thresholds(
    current_requests: int,
    request_limit: int,
    current_tokens: int,
    token_limit: int,
) -> list[UsageAlert]:
    """Check if usage crosses 80% or 100% thresholds.

    Returns a list of alerts for any thresholds exceeded.
    """
    alerts: list[UsageAlert] = []

    for resource, current, limit in [
        ("requests", current_requests, request_limit),
        ("tokens", current_tokens, token_limit),
    ]:
        if limit <= 0:
            continue
        pct = (current / limit) * 100
        if pct >= 100:
            alerts.append(UsageAlert(threshold_pct=100, resource=resource, current=current, limit=limit))
        elif pct >= 80:
            alerts.append(UsageAlert(threshold_pct=80, resource=resource, current=current, limit=limit))

    return alerts


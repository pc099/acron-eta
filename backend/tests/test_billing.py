import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.services.stripe import record_stripe_usage


def _auth_header(raw_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {raw_key}"}


async def test_billing_endpoints(
    client: AsyncClient,
    seed_org: dict[str, object],
) -> None:
    raw_key = seed_org["raw_key"]  # type: ignore[index]

    plans_resp = await client.get("/billing/plans", headers=_auth_header(raw_key))
    assert plans_resp.status_code == 200
    plans = plans_resp.json()
    assert any(plan["id"] == "free" for plan in plans)
    assert any(plan["id"] == "pro" for plan in plans)

    subscription_resp = await client.get("/billing/subscription", headers=_auth_header(raw_key))
    assert subscription_resp.status_code == 200
    subscription = subscription_resp.json()
    assert subscription["plan"] == "free"

    usage_resp = await client.get("/billing/usage", headers=_auth_header(raw_key))
    assert usage_resp.status_code == 200
    usage = usage_resp.json()
    assert usage["requests_used"] >= 0

    checkout_resp = await client.post(
        "/billing/checkout",
        json={
            "plan": "pro",
            "success_url": "https://example.com/success",
            "cancel_url": "https://example.com/cancel",
        },
        headers=_auth_header(raw_key),
    )
    assert checkout_resp.status_code == 200
    checkout = checkout_resp.json()
    assert "checkout_url" in checkout


# ---------------------------------------------------------------------------
# record_stripe_usage retry tests
# ---------------------------------------------------------------------------

def _fake_org(
    org_id: uuid.UUID | None = None,
    stripe_customer_id: str | None = "cus_test123",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=org_id or uuid.uuid4(),
        stripe_customer_id=stripe_customer_id,
    )


@pytest.mark.asyncio
async def test_record_usage_success() -> None:
    org = _fake_org()
    mock_create = MagicMock()
    with (
        patch("app.services.stripe._init_stripe", return_value=True),
        patch("app.services.stripe.stripe") as mock_stripe,
    ):
        mock_stripe.billing.MeterEvent.create = mock_create
        await record_stripe_usage(org, 500, "evt_1")
    mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_record_usage_retry_then_success() -> None:
    org = _fake_org()
    mock_create = MagicMock(side_effect=[RuntimeError("transient"), None])
    with (
        patch("app.services.stripe._init_stripe", return_value=True),
        patch("app.services.stripe.stripe") as mock_stripe,
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        mock_stripe.billing.MeterEvent.create = mock_create
        await record_stripe_usage(org, 100, "evt_2", max_retries=2)
    assert mock_create.call_count == 2


@pytest.mark.asyncio
async def test_record_usage_all_retries_exhausted() -> None:
    org = _fake_org()
    mock_create = MagicMock(side_effect=RuntimeError("permanent"))
    with (
        patch("app.services.stripe._init_stripe", return_value=True),
        patch("app.services.stripe.stripe") as mock_stripe,
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        mock_stripe.billing.MeterEvent.create = mock_create
        # Should not raise
        await record_stripe_usage(org, 100, "evt_3", max_retries=3)
    assert mock_create.call_count == 3


@pytest.mark.asyncio
async def test_record_usage_skips_zero_tokens() -> None:
    org = _fake_org()
    mock_create = MagicMock()
    with (
        patch("app.services.stripe._init_stripe", return_value=True),
        patch("app.services.stripe.stripe") as mock_stripe,
    ):
        mock_stripe.billing.MeterEvent.create = mock_create
        await record_stripe_usage(org, 0, "evt_4")
    mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_record_usage_skips_no_customer_id() -> None:
    org = _fake_org(stripe_customer_id=None)
    mock_create = MagicMock()
    with (
        patch("app.services.stripe._init_stripe", return_value=True),
        patch("app.services.stripe.stripe") as mock_stripe,
    ):
        mock_stripe.billing.MeterEvent.create = mock_create
        await record_stripe_usage(org, 100, "evt_5")
    mock_create.assert_not_called()


# -- Usage threshold alerts ------------------------------------------------

from app.services.stripe import check_usage_thresholds


class TestUsageThresholdAlerts:
    def test_no_alert_below_80_pct(self) -> None:
        alerts = check_usage_thresholds(
            current_requests=500, request_limit=10_000,
            current_tokens=50_000, token_limit=1_000_000,
        )
        assert alerts == []

    def test_alert_at_80_pct(self) -> None:
        alerts = check_usage_thresholds(
            current_requests=8_000, request_limit=10_000,
            current_tokens=100_000, token_limit=1_000_000,
        )
        assert len(alerts) == 1
        assert alerts[0].resource == "requests"
        assert alerts[0].threshold_pct == 80

    def test_alert_at_100_pct(self) -> None:
        alerts = check_usage_thresholds(
            current_requests=10_000, request_limit=10_000,
            current_tokens=100_000, token_limit=1_000_000,
        )
        assert len(alerts) == 1
        assert alerts[0].resource == "requests"
        assert alerts[0].threshold_pct == 100

    def test_multiple_resource_alerts(self) -> None:
        alerts = check_usage_thresholds(
            current_requests=9_000, request_limit=10_000,
            current_tokens=900_000, token_limit=1_000_000,
        )
        assert len(alerts) == 2
        resources = {a.resource for a in alerts}
        assert resources == {"requests", "tokens"}

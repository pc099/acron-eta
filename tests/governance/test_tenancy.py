"""Tests for MultiTenancyManager (tenant isolation)."""

import pytest

from src.governance.tenancy import MultiTenancyManager, Tenant, TenancyConfig


@pytest.fixture
def manager() -> MultiTenancyManager:
    return MultiTenancyManager()


@pytest.fixture
def seeded_manager(manager: MultiTenancyManager) -> MultiTenancyManager:
    manager.create_tenant(Tenant(org_id="acme", name="Acme Corp", plan="professional"))
    manager.create_tenant(Tenant(org_id="globex", name="Globex Inc", plan="enterprise"))
    return manager


# ── Tenant CRUD ────────────────────────────────────────


class TestTenantCRUD:
    def test_create_and_get(self, manager: MultiTenancyManager) -> None:
        t = Tenant(org_id="org-1", name="Test Org")
        manager.create_tenant(t)
        result = manager.get_tenant("org-1")
        assert result is not None
        assert result.name == "Test Org"
        assert result.plan == "starter"

    def test_create_duplicate_raises(
        self, seeded_manager: MultiTenancyManager
    ) -> None:
        with pytest.raises(ValueError, match="already exists"):
            seeded_manager.create_tenant(
                Tenant(org_id="acme", name="Duplicate")
            )

    def test_get_nonexistent(self, manager: MultiTenancyManager) -> None:
        assert manager.get_tenant("ghost") is None

    def test_enterprise_plan(
        self, seeded_manager: MultiTenancyManager
    ) -> None:
        t = seeded_manager.get_tenant("globex")
        assert t is not None
        assert t.plan == "enterprise"


# ── Access control ─────────────────────────────────────


class TestValidateAccess:
    def test_same_org_allowed(
        self, seeded_manager: MultiTenancyManager
    ) -> None:
        assert seeded_manager.validate_access("acme", "acme") is True

    def test_cross_tenant_denied(
        self, seeded_manager: MultiTenancyManager
    ) -> None:
        assert seeded_manager.validate_access("acme", "globex") is False

    def test_unknown_org_denied(
        self, seeded_manager: MultiTenancyManager
    ) -> None:
        assert seeded_manager.validate_access("acme", "unknown") is False


# ── Namespace isolation ────────────────────────────────


class TestCacheNamespace:
    def test_default_prefix(
        self, seeded_manager: MultiTenancyManager
    ) -> None:
        ns = seeded_manager.get_tenant_cache_namespace("acme")
        assert ns == "tenant:acme"

    def test_custom_prefix(self) -> None:
        cfg = TenancyConfig(cache_namespace_prefix="cache_v2")
        mgr = MultiTenancyManager(config=cfg)
        mgr.create_tenant(Tenant(org_id="org-x", name="X"))
        assert mgr.get_tenant_cache_namespace("org-x") == "cache_v2:org-x"

    def test_different_tenants_different_namespaces(
        self, seeded_manager: MultiTenancyManager
    ) -> None:
        ns1 = seeded_manager.get_tenant_cache_namespace("acme")
        ns2 = seeded_manager.get_tenant_cache_namespace("globex")
        assert ns1 != ns2


# ── Metrics / activity ─────────────────────────────────


class TestMetrics:
    def test_metrics_for_tenant(
        self, seeded_manager: MultiTenancyManager
    ) -> None:
        seeded_manager.record_tenant_activity("acme")
        seeded_manager.record_tenant_activity("acme")
        metrics = seeded_manager.get_tenant_metrics("acme")
        assert metrics["total_requests"] == 2
        assert metrics["plan"] == "professional"
        assert "limits" in metrics

    def test_metrics_nonexistent_tenant(
        self, manager: MultiTenancyManager
    ) -> None:
        metrics = manager.get_tenant_metrics("ghost")
        assert metrics["error"] == "tenant_not_found"

    def test_activity_isolated(
        self, seeded_manager: MultiTenancyManager
    ) -> None:
        seeded_manager.record_tenant_activity("acme")
        assert seeded_manager.get_tenant_metrics("globex")["total_requests"] == 0

    def test_plan_limits_in_metrics(
        self, seeded_manager: MultiTenancyManager
    ) -> None:
        metrics = seeded_manager.get_tenant_metrics("globex")
        assert metrics["limits"]["max_requests_per_day"] == 100_000

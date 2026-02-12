"""Tests for GovernanceEngine (RBAC + policy enforcement)."""

from datetime import datetime

import pytest

from src.exceptions import BudgetExceededError, PermissionDeniedError
from src.governance.rbac import (
    DEFAULT_ROLES,
    GovernanceConfig,
    GovernanceEngine,
    Organization,
    OrganizationPolicy,
    Role,
    User,
)


@pytest.fixture
def engine() -> GovernanceEngine:
    return GovernanceEngine()


@pytest.fixture
def seeded_engine(engine: GovernanceEngine) -> GovernanceEngine:
    """Engine with org, users, and policy pre-configured."""
    engine.register_user(
        User(user_id="admin-1", email="admin@acme.com", org_id="org-1", role="admin")
    )
    engine.register_user(
        User(user_id="dev-1", email="dev@acme.com", org_id="org-1", role="developer")
    )
    engine.register_user(
        User(
            user_id="viewer-1",
            email="viewer@acme.com",
            org_id="org-1",
            role="viewer",
        )
    )
    engine.register_user(
        User(
            user_id="billing-1",
            email="billing@acme.com",
            org_id="org-1",
            role="billing",
        )
    )
    engine.create_policy(
        OrganizationPolicy(
            org_id="org-1",
            blocked_models=["gpt-4-expensive"],
            allowed_models=["claude-3-5-sonnet", "gpt-4-turbo"],
            max_cost_per_request=1.0,
            max_cost_per_day=100.0,
            max_requests_per_day=1000,
        )
    )
    return engine


# ── Default roles ──────────────────────────────────────


class TestDefaultRoles:
    def test_admin_has_all_permissions(self) -> None:
        assert len(DEFAULT_ROLES["admin"].permissions) == 8

    def test_developer_permissions(self) -> None:
        perms = DEFAULT_ROLES["developer"].permissions
        assert "infer" in perms
        assert "view_metrics" in perms
        assert "view_cost" in perms
        assert "manage_users" not in perms

    def test_viewer_permissions(self) -> None:
        perms = DEFAULT_ROLES["viewer"].permissions
        assert perms == ["view_metrics"]

    def test_billing_permissions(self) -> None:
        perms = DEFAULT_ROLES["billing"].permissions
        assert "view_cost" in perms
        assert "manage_billing" in perms
        assert "view_audit_log" in perms
        assert "infer" not in perms


# ── Permission checks ─────────────────────────────────


class TestCheckPermission:
    def test_admin_can_infer(self, seeded_engine: GovernanceEngine) -> None:
        assert seeded_engine.check_permission("admin-1", "org-1", "infer")

    def test_developer_can_infer(self, seeded_engine: GovernanceEngine) -> None:
        assert seeded_engine.check_permission("dev-1", "org-1", "infer")

    def test_viewer_cannot_infer(self, seeded_engine: GovernanceEngine) -> None:
        assert not seeded_engine.check_permission("viewer-1", "org-1", "infer")

    def test_billing_cannot_infer(self, seeded_engine: GovernanceEngine) -> None:
        assert not seeded_engine.check_permission("billing-1", "org-1", "infer")

    def test_unknown_user(self, seeded_engine: GovernanceEngine) -> None:
        assert not seeded_engine.check_permission("ghost", "org-1", "infer")

    def test_wrong_org(self, seeded_engine: GovernanceEngine) -> None:
        assert not seeded_engine.check_permission("admin-1", "org-other", "infer")

    def test_admin_manage_users(self, seeded_engine: GovernanceEngine) -> None:
        assert seeded_engine.check_permission("admin-1", "org-1", "manage_users")

    def test_developer_cannot_manage_users(
        self, seeded_engine: GovernanceEngine
    ) -> None:
        assert not seeded_engine.check_permission("dev-1", "org-1", "manage_users")


# ── Role management ────────────────────────────────────


class TestRoleManagement:
    def test_get_user_role(self, seeded_engine: GovernanceEngine) -> None:
        role = seeded_engine.get_user_role("admin-1", "org-1")
        assert role.name == "admin"

    def test_get_user_role_not_found(
        self, seeded_engine: GovernanceEngine
    ) -> None:
        with pytest.raises(PermissionDeniedError):
            seeded_engine.get_user_role("ghost", "org-1")

    def test_assign_role(self, seeded_engine: GovernanceEngine) -> None:
        seeded_engine.assign_role("dev-1", "org-1", "admin")
        assert seeded_engine.check_permission("dev-1", "org-1", "manage_users")

    def test_assign_invalid_role(self, seeded_engine: GovernanceEngine) -> None:
        with pytest.raises(PermissionDeniedError):
            seeded_engine.assign_role("dev-1", "org-1", "nonexistent_role")

    def test_list_org_users(self, seeded_engine: GovernanceEngine) -> None:
        users = seeded_engine.list_org_users("org-1")
        assert len(users) == 4


# ── Policy enforcement ─────────────────────────────────


class TestEnforcePolicy:
    def test_allowed_model_passes(self, seeded_engine: GovernanceEngine) -> None:
        ok, reason = seeded_engine.enforce_policy("org-1", "claude-3-5-sonnet", 0.01)
        assert ok
        assert reason is None

    def test_blocked_model_rejected(self, seeded_engine: GovernanceEngine) -> None:
        ok, reason = seeded_engine.enforce_policy("org-1", "gpt-4-expensive", 0.01)
        assert not ok
        assert "blocked" in reason

    def test_model_not_in_allowed_list(
        self, seeded_engine: GovernanceEngine
    ) -> None:
        ok, reason = seeded_engine.enforce_policy("org-1", "unknown-model", 0.01)
        assert not ok
        assert "not in the allowed" in reason

    def test_empty_allowed_means_all_ok(self, engine: GovernanceEngine) -> None:
        engine.create_policy(OrganizationPolicy(org_id="org-2"))
        ok, reason = engine.enforce_policy("org-2", "any-model", 0.01)
        assert ok

    def test_cost_per_request_exceeded(
        self, seeded_engine: GovernanceEngine
    ) -> None:
        ok, reason = seeded_engine.enforce_policy("org-1", "claude-3-5-sonnet", 5.0)
        assert not ok
        assert "per-request limit" in reason

    def test_no_policy_allows_all(self, engine: GovernanceEngine) -> None:
        ok, reason = engine.enforce_policy("no-policy-org", "any-model", 999.0)
        assert ok


# ── Budget tracking ────────────────────────────────────


class TestBudgetTracking:
    def test_within_budget(self, seeded_engine: GovernanceEngine) -> None:
        ok, reason = seeded_engine.check_budget("org-1", 50.0)
        assert ok

    def test_budget_exceeded(self, seeded_engine: GovernanceEngine) -> None:
        # Spend up to the limit
        for _ in range(10):
            seeded_engine.record_spend("org-1", 10.0)

        ok, reason = seeded_engine.check_budget("org-1", 1.0)
        assert not ok
        assert "Daily budget exceeded" in reason

    def test_record_spend_tracks_requests(
        self, seeded_engine: GovernanceEngine
    ) -> None:
        seeded_engine.record_spend("org-1", 1.0)
        assert seeded_engine._count_requests_today("org-1") == 1

    def test_request_limit_enforcement(
        self, seeded_engine: GovernanceEngine
    ) -> None:
        # Set a low request limit
        seeded_engine.update_policy("org-1", {"max_requests_per_day": 3})

        for _ in range(3):
            seeded_engine.record_spend("org-1", 0.01)

        ok, reason = seeded_engine.enforce_policy(
            "org-1", "claude-3-5-sonnet", 0.01
        )
        assert not ok
        assert "request limit" in reason


# ── Policy CRUD ────────────────────────────────────────


class TestPolicyCRUD:
    def test_create_and_get(self, engine: GovernanceEngine) -> None:
        policy = OrganizationPolicy(org_id="org-x", max_cost_per_day=50.0)
        engine.create_policy(policy)
        retrieved = engine.get_policy("org-x")
        assert retrieved is not None
        assert retrieved.max_cost_per_day == 50.0

    def test_update_policy(self, seeded_engine: GovernanceEngine) -> None:
        seeded_engine.update_policy("org-1", {"max_cost_per_day": 200.0})
        p = seeded_engine.get_policy("org-1")
        assert p.max_cost_per_day == 200.0

    def test_update_nonexistent(self, engine: GovernanceEngine) -> None:
        with pytest.raises(PermissionDeniedError):
            engine.update_policy("no-org", {"max_cost_per_day": 10.0})

    def test_get_nonexistent(self, engine: GovernanceEngine) -> None:
        assert engine.get_policy("no-org") is None

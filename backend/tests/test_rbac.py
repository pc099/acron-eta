"""Tests for RBAC enforcement middleware."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.models import MemberRole
from app.middleware.rbac import require_role


# ---------------------------------------------------------------------------
# Tiny FastAPI app for testing the dependency in isolation
# ---------------------------------------------------------------------------

def _build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/admin-only", dependencies=[require_role(MemberRole.ADMIN)])
    async def admin_only():
        return {"ok": True}

    @app.get("/member-only", dependencies=[require_role(MemberRole.MEMBER)])
    async def member_only():
        return {"ok": True}

    @app.get("/viewer-only", dependencies=[require_role(MemberRole.VIEWER)])
    async def viewer_only():
        return {"ok": True}

    @app.get("/owner-only", dependencies=[require_role(MemberRole.OWNER)])
    async def owner_only():
        return {"ok": True}

    return app


def _set_state(app: FastAPI, auth_type: str, role: MemberRole | None = None) -> None:
    """Add middleware that populates request.state for testing."""
    from starlette.middleware.base import BaseHTTPMiddleware

    class _FakeAuth(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            request.state.auth_type = auth_type
            request.state.role = role
            return await call_next(request)

    app.add_middleware(_FakeAuth)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRBACHierarchy:
    """Verify that the role hierarchy is enforced correctly."""

    def test_owner_passes_admin_check(self) -> None:
        app = _build_app()
        _set_state(app, "jwt", MemberRole.OWNER)
        resp = TestClient(app).get("/admin-only")
        assert resp.status_code == 200

    def test_admin_passes_admin_check(self) -> None:
        app = _build_app()
        _set_state(app, "jwt", MemberRole.ADMIN)
        resp = TestClient(app).get("/admin-only")
        assert resp.status_code == 200

    def test_member_fails_admin_check(self) -> None:
        app = _build_app()
        _set_state(app, "jwt", MemberRole.MEMBER)
        resp = TestClient(app).get("/admin-only")
        assert resp.status_code == 403

    def test_viewer_fails_admin_check(self) -> None:
        app = _build_app()
        _set_state(app, "jwt", MemberRole.VIEWER)
        resp = TestClient(app).get("/admin-only")
        assert resp.status_code == 403

    def test_member_passes_member_check(self) -> None:
        app = _build_app()
        _set_state(app, "jwt", MemberRole.MEMBER)
        resp = TestClient(app).get("/member-only")
        assert resp.status_code == 200

    def test_viewer_passes_viewer_check(self) -> None:
        app = _build_app()
        _set_state(app, "jwt", MemberRole.VIEWER)
        resp = TestClient(app).get("/viewer-only")
        assert resp.status_code == 200

    def test_viewer_fails_member_check(self) -> None:
        app = _build_app()
        _set_state(app, "jwt", MemberRole.VIEWER)
        resp = TestClient(app).get("/member-only")
        assert resp.status_code == 403


class TestRBACEdgeCases:
    """Edge cases: API key bypass, missing role, error payload."""

    def test_api_key_bypasses_rbac(self) -> None:
        app = _build_app()
        _set_state(app, "api_key", role=None)
        resp = TestClient(app).get("/owner-only")
        assert resp.status_code == 200

    def test_no_role_returns_403(self) -> None:
        app = _build_app()
        _set_state(app, "jwt", role=None)
        resp = TestClient(app).get("/admin-only")
        assert resp.status_code == 403
        body = resp.json()
        assert body["detail"]["error"]["code"] == "INSUFFICIENT_ROLE"

    def test_error_includes_required_role(self) -> None:
        app = _build_app()
        _set_state(app, "jwt", MemberRole.VIEWER)
        resp = TestClient(app).get("/admin-only")
        body = resp.json()
        assert "admin" in body["detail"]["error"]["message"].lower()

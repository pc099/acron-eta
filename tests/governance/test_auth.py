"""Tests for AuthMiddleware (API key authentication)."""

from datetime import datetime, timedelta

import pytest

from src.governance.auth import AuthConfig, AuthMiddleware, AuthResult


@pytest.fixture
def auth() -> AuthMiddleware:
    return AuthMiddleware(config=AuthConfig(api_key_required=True))


# ── Key generation ─────────────────────────────────────


class TestGenerateKey:
    def test_key_format(self, auth: AuthMiddleware) -> None:
        key = auth.generate_api_key("user-1", "acme-corp", scopes=["infer"])
        assert key.startswith("ask_acme_")
        # ask_ + 4-char org prefix + _ + 32 hex chars = 41 total
        parts = key.split("_")
        assert len(parts) == 3
        assert len(parts[2]) == 32

    def test_unique_keys(self, auth: AuthMiddleware) -> None:
        k1 = auth.generate_api_key("user-1", "org-1")
        k2 = auth.generate_api_key("user-1", "org-1")
        assert k1 != k2

    def test_short_org_id(self, auth: AuthMiddleware) -> None:
        key = auth.generate_api_key("user-1", "ab")
        assert key.startswith("ask_ab_")


# ── Key validation ─────────────────────────────────────


class TestValidateKey:
    def test_valid_key(self, auth: AuthMiddleware) -> None:
        key = auth.generate_api_key("user-1", "org-1", scopes=["infer"])
        result = auth.validate_api_key(key)
        assert result.authenticated is True
        assert result.user_id == "user-1"
        assert result.org_id == "org-1"
        assert "infer" in result.scopes

    def test_invalid_key(self, auth: AuthMiddleware) -> None:
        result = auth.validate_api_key("ask_fake_0000000000000000")
        assert result.authenticated is False

    def test_empty_key(self, auth: AuthMiddleware) -> None:
        result = auth.validate_api_key("")
        assert result.authenticated is False

    def test_expired_key(self, auth: AuthMiddleware) -> None:
        key = auth.generate_api_key("user-1", "org-1")
        prefix = key[:12]
        # Force expiration by backdating
        auth._keys[prefix].expires_at = datetime.utcnow() - timedelta(days=1)
        result = auth.validate_api_key(key)
        assert result.authenticated is False

    def test_revoked_key(self, auth: AuthMiddleware) -> None:
        key = auth.generate_api_key("user-1", "org-1")
        prefix = key[:12]
        auth.revoke_api_key(prefix)
        result = auth.validate_api_key(key)
        assert result.authenticated is False

    def test_tampered_key_fails(self, auth: AuthMiddleware) -> None:
        key = auth.generate_api_key("user-1", "org-1")
        tampered = key[:-1] + ("a" if key[-1] != "a" else "b")
        result = auth.validate_api_key(tampered)
        assert result.authenticated is False


# ── Request authentication ─────────────────────────────


class TestAuthenticate:
    def test_with_bearer_header(self, auth: AuthMiddleware) -> None:
        key = auth.generate_api_key("user-1", "org-1")
        result = auth.authenticate({"Authorization": f"Bearer {key}"})
        assert result.authenticated is True
        assert result.user_id == "user-1"

    def test_lowercase_header(self, auth: AuthMiddleware) -> None:
        key = auth.generate_api_key("user-1", "org-1")
        result = auth.authenticate({"authorization": f"Bearer {key}"})
        assert result.authenticated is True

    def test_missing_header(self, auth: AuthMiddleware) -> None:
        result = auth.authenticate({})
        assert result.authenticated is False

    def test_wrong_scheme(self, auth: AuthMiddleware) -> None:
        result = auth.authenticate({"Authorization": "Basic abc123"})
        assert result.authenticated is False

    def test_auth_not_required(self) -> None:
        cfg = AuthConfig(api_key_required=False)
        a = AuthMiddleware(config=cfg)
        result = a.authenticate({})
        assert result.authenticated is True
        assert "*" in result.scopes


# ── Key revocation ─────────────────────────────────────


class TestRevocation:
    def test_revoke_existing(self, auth: AuthMiddleware) -> None:
        key = auth.generate_api_key("user-1", "org-1")
        prefix = key[:12]
        assert auth.revoke_api_key(prefix) is True

    def test_revoke_nonexistent(self, auth: AuthMiddleware) -> None:
        assert auth.revoke_api_key("ask_xxxx_xxx") is False

    def test_revoked_key_cannot_auth(self, auth: AuthMiddleware) -> None:
        key = auth.generate_api_key("user-1", "org-1")
        prefix = key[:12]
        auth.revoke_api_key(prefix)
        result = auth.authenticate({"Authorization": f"Bearer {key}"})
        assert result.authenticated is False

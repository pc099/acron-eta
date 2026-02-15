"""
API key authentication middleware.

Generates, validates, and revokes API keys with bcrypt hashing
and configurable expiration.  Keys follow the format
``ask_{org_prefix}_{random_hex}``.

When a key_store is provided (e.g. DbKeyStore for PostgreSQL),
keys are persisted and validated from the store.
"""

import logging
import secrets
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Protocol

import bcrypt
from pydantic import BaseModel, Field

from src.config import get_settings

logger = logging.getLogger(__name__)


class KeyStoreProtocol(Protocol):
    """Protocol for key storage (in-memory or DB)."""

    def get_by_prefix(self, key_prefix: str) -> Optional["_StoredKey"]:
        """Return stored key by 12-char prefix, or None."""
        ...

    def store(self, stored: "_StoredKey", full_key: str) -> None:
        """Persist a new key."""
        ...

    def revoke_by_prefix(self, key_prefix: str) -> bool:
        """Revoke key by prefix. Returns True if found and revoked."""
        ...


# ── Data Models ────────────────────────────────────────


class AuthConfig(BaseModel):
    """Configuration for AuthMiddleware.

    Attributes:
        api_key_required: Whether requests must provide a key.
        key_expiry_days: Default key lifetime in days.
        key_prefix: Prefix for generated API keys.
    """

    api_key_required: bool = True
    key_expiry_days: int = Field(default=90, ge=1)
    key_prefix: str = "ask"


class AuthResult(BaseModel):
    """Result of an authentication attempt.

    Attributes:
        authenticated: Whether the request passed authentication.
        user_id: Authenticated user ID.
        org_id: Authenticated organisation ID.
        plan: Subscription plan of the org.
        scopes: Granted permission scopes.
    """

    authenticated: bool = False
    user_id: Optional[str] = None
    org_id: Optional[str] = None
    plan: Optional[str] = None
    scopes: List[str] = Field(default_factory=list)


class _StoredKey(BaseModel):
    """Internal representation of a stored API key.

    Attributes:
        key_display_prefix: First 12 chars for identification.
        key_hash: bcrypt hash of the full key.
        user_id: Owner user ID.
        org_id: Owner organisation ID.
        scopes: Permission scopes.
        expires_at: Expiration timestamp.
        revoked: Whether the key has been revoked.
        created_at: Creation timestamp.
    """

    key_display_prefix: str
    key_hash: str
    user_id: str
    org_id: str
    scopes: List[str] = Field(default_factory=list)
    expires_at: datetime = Field(default_factory=datetime.utcnow)
    revoked: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AuthMiddleware:
    """API key authentication manager.

    Args:
        config: Authentication configuration.
        key_store: Optional store for keys (e.g. DbKeyStore). When set,
            validate and generate use it; otherwise in-memory only.
    """

    def __init__(
        self,
        config: Optional[AuthConfig] = None,
        key_store: Optional[KeyStoreProtocol] = None,
    ) -> None:
        if config is None:
            _s = get_settings().governance
            config = AuthConfig(
                api_key_required=_s.auth_api_key_required,
                key_expiry_days=_s.auth_key_expiry_days,
                key_prefix=_s.auth_key_prefix,
            )
        self._config = config
        self._key_store = key_store
        self._lock = threading.Lock()
        # key_display_prefix -> _StoredKey (in-memory cache when no key_store)
        self._keys: Dict[str, _StoredKey] = {}
        logger.info(
            "AuthMiddleware initialised",
            extra={"key_store": "db" if key_store else "memory"},
        )

    # ------------------------------------------------------------------
    # Key generation
    # ------------------------------------------------------------------

    def generate_api_key(
        self,
        user_id: str,
        org_id: str,
        scopes: Optional[List[str]] = None,
    ) -> str:
        """Generate a new API key.

        Args:
            user_id: Owner user ID.
            org_id: Owner organisation ID.
            scopes: Permission scopes for the key.

        Returns:
            The full API key string (only shown once).
        """
        scopes = scopes or []
        org_prefix = org_id[:4].lower()
        random_part = secrets.token_hex(16)
        full_key = f"{self._config.key_prefix}_{org_prefix}_{random_part}"

        key_hash = bcrypt.hashpw(
            full_key.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

        display_prefix = full_key[:12]
        expires_at = datetime.utcnow() + timedelta(
            days=self._config.key_expiry_days
        )

        stored = _StoredKey(
            key_display_prefix=display_prefix,
            key_hash=key_hash,
            user_id=user_id,
            org_id=org_id,
            scopes=scopes,
            expires_at=expires_at,
            created_at=datetime.utcnow(),
        )

        with self._lock:
            self._keys[display_prefix] = stored

        if self._key_store is not None:
            try:
                self._key_store.store(stored, full_key)
            except Exception as e:
                logger.error(
                    "Failed to persist API key to store",
                    extra={"prefix": display_prefix, "error": str(e)},
                )
                with self._lock:
                    self._keys.pop(display_prefix, None)
                raise

        logger.info(
            "API key generated",
            extra={
                "user_id": user_id,
                "org_id": org_id,
                "prefix": display_prefix,
            },
        )
        return full_key

    # ------------------------------------------------------------------
    # Key validation
    # ------------------------------------------------------------------

    def validate_api_key(self, key: str) -> AuthResult:
        """Validate an API key and return auth context.

        Args:
            key: The full API key string.

        Returns:
            AuthResult with authentication status and identity.
        """
        if not key:
            return AuthResult(authenticated=False)

        display_prefix = key[:12]
        stored: Optional[_StoredKey] = None
        if self._key_store is not None:
            try:
                stored = self._key_store.get_by_prefix(display_prefix)
            except Exception as e:
                logger.warning(
                    "Key store get failed",
                    extra={"prefix": display_prefix, "error": str(e)},
                )
        if stored is None:
            with self._lock:
                stored = self._keys.get(display_prefix)

        if not stored:
            logger.warning(
                "API key not found",
                extra={"prefix": display_prefix},
            )
            return AuthResult(authenticated=False)

        # Check revocation
        if stored.revoked:
            logger.warning(
                "Revoked API key used",
                extra={"prefix": display_prefix},
            )
            return AuthResult(authenticated=False)

        # Check expiration (use timezone-aware UTC to match DB/stored values)
        now = datetime.now(timezone.utc)
        expires_at = stored.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if now > expires_at:
            logger.warning(
                "Expired API key used",
                extra={"prefix": display_prefix},
            )
            return AuthResult(authenticated=False)

        # Verify bcrypt hash
        if not bcrypt.checkpw(
            key.encode("utf-8"), stored.key_hash.encode("utf-8")
        ):
            logger.warning(
                "API key hash mismatch",
                extra={"prefix": display_prefix},
            )
            return AuthResult(authenticated=False)

        return AuthResult(
            authenticated=True,
            user_id=stored.user_id,
            org_id=stored.org_id,
            scopes=stored.scopes,
        )

    # ------------------------------------------------------------------
    # Request authentication
    # ------------------------------------------------------------------

    def authenticate(self, headers: Dict[str, str]) -> AuthResult:
        """Authenticate a request from its headers.

        Accepts ``Authorization: Bearer ask_...`` or ``x-api-key: ask_...``
        (e.g. for dashboard and API docs). When API key is not required,
        still validates the key if present so org_id is set for dashboard scoping.
        """
        key: Optional[str] = None
        auth_header = (
            headers.get("authorization")
            or headers.get("Authorization")
            or ""
        )
        if auth_header.startswith("Bearer "):
            key = auth_header[7:].strip()
        if not key:
            key = (
                headers.get("x-api-key")
                or headers.get("X-Api-Key")
                or ""
            ).strip()

        if key:
            result = self.validate_api_key(key)
            if result.authenticated:
                return result
            if self._config.api_key_required:
                return result

        if not self._config.api_key_required:
            return AuthResult(authenticated=True, scopes=["*"])
        return AuthResult(authenticated=False)

    # ------------------------------------------------------------------
    # Key revocation
    # ------------------------------------------------------------------

    def revoke_api_key(self, key_display_prefix: str) -> bool:
        """Revoke an API key by its display prefix.

        Args:
            key_display_prefix: The first 12 chars of the key.

        Returns:
            True if the key was found and revoked, False otherwise.
        """
        found = False
        with self._lock:
            stored = self._keys.get(key_display_prefix)
            if stored:
                stored.revoked = True
                found = True
        if self._key_store is not None:
            try:
                found = (
                    self._key_store.revoke_by_prefix(key_display_prefix) or found
                )
            except Exception as e:
                logger.warning(
                    "Key store revoke failed",
                    extra={"prefix": key_display_prefix, "error": str(e)},
                )
        if found:
            logger.info(
                "API key revoked",
                extra={"prefix": key_display_prefix},
            )
        return found

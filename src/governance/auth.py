"""
API key authentication middleware.

Generates, validates, and revokes API keys with bcrypt hashing
and configurable expiration.  Keys follow the format
``ask_{org_prefix}_{random_hex}``.
"""

import logging
import secrets
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import bcrypt
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


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
    """

    def __init__(self, config: Optional[AuthConfig] = None) -> None:
        self._config = config or AuthConfig()
        self._lock = threading.Lock()
        # key_display_prefix -> _StoredKey
        self._keys: Dict[str, _StoredKey] = {}
        logger.info("AuthMiddleware initialised", extra={})

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

        # Check expiration
        if datetime.utcnow() > stored.expires_at:
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

        Expects ``Authorization: Bearer ask_...``.

        Args:
            headers: Request headers dict.

        Returns:
            AuthResult with authentication status.
        """
        if not self._config.api_key_required:
            return AuthResult(authenticated=True, scopes=["*"])

        auth_header = headers.get("authorization") or headers.get(
            "Authorization", ""
        )
        if not auth_header.startswith("Bearer "):
            return AuthResult(authenticated=False)

        key = auth_header[7:].strip()
        return self.validate_api_key(key)

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
        with self._lock:
            stored = self._keys.get(key_display_prefix)
            if not stored:
                return False
            stored.revoked = True

        logger.info(
            "API key revoked",
            extra={"prefix": key_display_prefix},
        )
        return True

"""
Database-backed API key store for AuthMiddleware.

Converts between ApiKeyModel and auth._StoredKey. Used when DATABASE_URL is set.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from src.db.repositories import ApiKeyRepository
from src.governance.auth import _StoredKey

if TYPE_CHECKING:
    from src.db.models import ApiKeyModel

logger = logging.getLogger(__name__)


def _row_to_stored(row: ApiKeyModel) -> _StoredKey:
    """Map an ApiKeyModel row to _StoredKey."""
    scopes: list = row.scopes if row.scopes is not None else []
    return _StoredKey(
        key_display_prefix=row.key_prefix,
        key_hash=row.key_hash,
        user_id=row.user_id,
        org_id=row.org_id,
        scopes=scopes,
        expires_at=row.expires_at,
        revoked=row.revoked,
        created_at=row.created_at,
    )


class DbKeyStore:
    """Key store that reads/writes API keys from PostgreSQL.

    Args:
        repository: ApiKeyRepository instance.
    """

    def __init__(self, repository: ApiKeyRepository) -> None:
        self._repo = repository

    def get_by_prefix(self, key_prefix: str) -> Optional[_StoredKey]:
        """Load a stored key by its 12-char prefix.

        Args:
            key_prefix: First 12 characters of the API key.

        Returns:
            _StoredKey if found, None otherwise.
        """
        row = self._repo.get_by_prefix(key_prefix)
        if row is None:
            return None
        return _row_to_stored(row)

    def store(self, stored: _StoredKey, full_key: str) -> None:
        """Persist a new API key (called after bcrypt hash is computed).

        Args:
            stored: _StoredKey with key_hash, user_id, org_id, etc.
            full_key: The full key string (only used to verify prefix match).
        """
        if full_key[:12] != stored.key_display_prefix:
            raise ValueError("full_key prefix does not match stored.key_display_prefix")
        self._repo.store(
            key_prefix=stored.key_display_prefix,
            key_hash=stored.key_hash,
            user_id=stored.user_id,
            org_id=stored.org_id,
            scopes=stored.scopes,
            expires_at=stored.expires_at,
        )
        logger.info(
            "API key stored in DB",
            extra={"key_prefix": stored.key_display_prefix, "org_id": stored.org_id},
        )

    def revoke_by_prefix(self, key_prefix: str) -> bool:
        """Revoke an API key by its 12-char prefix.

        Args:
            key_prefix: First 12 characters of the key.

        Returns:
            True if the key was found and revoked, False otherwise.
        """
        return self._repo.revoke_by_prefix(key_prefix)

"""
Repository for API keys (PostgreSQL).

Used by AuthMiddleware when DATABASE_URL is set.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import ApiKeyModel, OrgModel

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]


class ApiKeyRepository:
    """Repository for api_keys table.

    Args:
        session_factory: Callable that returns a new Session (e.g. from get_session_factory).
    """

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def get_by_prefix(self, key_prefix: str) -> Optional[ApiKeyModel]:
        """Fetch an API key row by its 12-char prefix.

        Args:
            key_prefix: First 12 characters of the API key.

        Returns:
            ApiKeyModel if found, None otherwise.
        """
        session: Session = self._session_factory()
        try:
            stmt = select(ApiKeyModel).where(
                ApiKeyModel.key_prefix == key_prefix
            )
            return session.execute(stmt).scalar_one_or_none()
        finally:
            session.close()

    def store(
        self,
        key_prefix: str,
        key_hash: str,
        user_id: str,
        org_id: str,
        scopes: Optional[List[str]] = None,
        expires_at: Optional[datetime] = None,
    ) -> ApiKeyModel:
        """Insert a new API key row.

        Args:
            key_prefix: First 12 chars of the key.
            key_hash: bcrypt hash of the full key.
            user_id: Owner user ID.
            org_id: Organisation ID.
            scopes: Optional list of scope strings.
            expires_at: Expiration timestamp.

        Returns:
            The created ApiKeyModel instance.

        Raises:
            ValueError: If expires_at is None.
        """
        if expires_at is None:
            raise ValueError("expires_at is required")
        session: Session = self._session_factory()
        try:
            row = ApiKeyModel(
                key_prefix=key_prefix,
                key_hash=key_hash,
                user_id=user_id,
                org_id=org_id,
                scopes=scopes or [],
                expires_at=expires_at,
                revoked=False,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            logger.info(
                "API key stored",
                extra={"key_prefix": key_prefix, "org_id": org_id},
            )
            return row
        finally:
            session.close()

    def revoke_by_prefix(self, key_prefix: str) -> bool:
        """Revoke an API key by its prefix.

        Args:
            key_prefix: First 12 characters of the key.

        Returns:
            True if a row was updated, False if not found.
        """
        session: Session = self._session_factory()
        try:
            stmt = select(ApiKeyModel).where(
                ApiKeyModel.key_prefix == key_prefix
            )
            row = session.execute(stmt).scalar_one_or_none()
            if not row:
                return False
            row.revoked = True
            session.commit()
            logger.info("API key revoked", extra={"key_prefix": key_prefix})
            return True
        finally:
            session.close()


class OrgRepository:
    """Repository for orgs table."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def create_org(self, name: str, plan: str = "startup") -> OrgModel:
        """Create a new organisation.

        Args:
            name: Display name for the organisation.
            plan: Plan name (e.g. startup, business, enterprise).

        Returns:
            The created OrgModel instance.
        """
        session: Session = self._session_factory()
        try:
            row = OrgModel(name=name, plan=plan)
            session.add(row)
            session.commit()
            session.refresh(row)
            logger.info("Org created", extra={"org_id": row.id, "name": name})
            return row
        finally:
            session.close()



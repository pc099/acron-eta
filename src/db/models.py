"""
SQLAlchemy models for orgs and API keys.

Used for persistence when DATABASE_URL is set (e.g. Railway Postgres).
"""

from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.db.engine import Base


class OrgModel(Base):
    """Organization/tenant for multi-tenancy.

    Attributes:
        id: Primary key.
        name: Display name.
        plan: Subscription plan (e.g. startup, business, enterprise).
        created_at: Creation timestamp.
    """

    __tablename__ = "orgs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    plan: Mapped[str] = mapped_column(String(64), nullable=False, default="startup")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )


class ApiKeyModel(Base):
    """Stored API key (hash and metadata).

    Attributes:
        id: Primary key.
        key_prefix: First 12 chars of key (unique lookup).
        key_hash: bcrypt hash of full key.
        user_id: Owner user ID.
        org_id: FK to orgs (denormalized for fast lookup).
        scopes: JSON array of scope strings.
        expires_at: Expiration timestamp.
        revoked: Whether the key is revoked.
        created_at: Creation timestamp.
    """

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key_prefix: Mapped[str] = mapped_column(String(12), unique=True, nullable=False, index=True)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    org_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    scopes: Mapped[Optional[List[Any]]] = mapped_column(JSONB, nullable=True, default=list)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # org_id is stored as string (e.g. str(OrgModel.id)); no FK to OrgModel to keep schema simple.
</think>
Fixing the ApiKey model: keep `org_id` as a string (no FK) for simplicity.
<｜tool▁calls▁begin｜><｜tool▁call▁begin｜>
StrReplace
"""
SQLAlchemy models for orgs and API keys.

Used for persistence when DATABASE_URL is set (e.g. Railway Postgres).
"""

from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

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

    api_keys: Mapped[List["ApiKeyModel"]] = relationship(
        "ApiKeyModel", back_populates="org", cascade="all, delete-orphan"
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

    org: Mapped[Optional["OrgModel"]] = relationship(
        "OrgModel", back_populates="api_keys", foreign_keys=[org_id]
    )


# Fix relationship: ApiKeyModel.org_id should reference OrgModel.id if we use FK.
# For minimal schema we keep org_id as string (external id) so we don't require
# orgs to exist before keys. Remove the foreign_keys if we're not using FK.
# Actually the roadmap had org_id as VARCHAR, so we store org_id as string (e.g. uuid or slug).
# So no FK from api_keys to orgs; we just have both tables. Remove the relationship
# from ApiKeyModel to OrgModel to avoid needing org_id as integer FK.
# I'll remove the relationship from ApiKeyModel to OrgModel and keep org_id as string.
</think>
Fixing the ApiKey model: keep `org_id` as a string (no FK) for simplicity.
<｜tool▁calls▁begin｜><｜tool▁call▁begin｜>
StrReplace
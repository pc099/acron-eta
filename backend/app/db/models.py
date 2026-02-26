"""SQLAlchemy 2.0 ORM models for ASAHI SaaS platform.

Defines the complete database schema: organisations, users, members,
API keys, request logs, usage snapshots, audit logs, and invitations.
"""

import enum
import hashlib
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


def utcnow() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


# ──────────────────────────────────────────
# ENUMS
# ──────────────────────────────────────────

class PlanTier(str, enum.Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class MemberRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class KeyEnvironment(str, enum.Enum):
    LIVE = "live"
    TEST = "test"


class CacheType(str, enum.Enum):
    EXACT = "exact"
    SEMANTIC = "semantic"
    INTERMEDIATE = "intermediate"
    MISS = "miss"


# ──────────────────────────────────────────
# ORGANISATIONS (Tenants)
# ──────────────────────────────────────────

class Organisation(Base):
    """Top-level tenant. Every resource is scoped to an organisation."""
    __tablename__ = "organisations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    plan: Mapped[PlanTier] = mapped_column(
        SAEnum(PlanTier), default=PlanTier.FREE, nullable=False
    )

    # Stripe
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, nullable=True
    )
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, nullable=True
    )

    # Plan limits (can be overridden per-org for enterprise)
    monthly_request_limit: Mapped[int] = mapped_column(Integer, default=10_000)
    monthly_token_limit: Mapped[int] = mapped_column(Integer, default=1_000_000)
    monthly_budget_usd: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 4), nullable=True
    )

    metadata_: Mapped[Optional[dict]] = mapped_column(
        "metadata", JSONB, default=dict
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    members: Mapped[list["Member"]] = relationship(
        back_populates="organisation", cascade="all, delete-orphan"
    )
    api_keys: Mapped[list["ApiKey"]] = relationship(
        back_populates="organisation", cascade="all, delete-orphan"
    )
    request_logs: Mapped[list["RequestLog"]] = relationship(
        back_populates="organisation"
    )
    usage_snapshots: Mapped[list["UsageSnapshot"]] = relationship(
        back_populates="organisation"
    )


# ──────────────────────────────────────────
# USERS (Global pool — shared across orgs)
# ──────────────────────────────────────────

class User(Base):
    """A user who can belong to multiple organisations via memberships."""
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # External auth provider ID (Clerk user ID)
    clerk_user_id: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    memberships: Mapped[list["Member"]] = relationship(back_populates="user")


# ──────────────────────────────────────────
# MEMBERS (User ↔ Organisation junction)
# ──────────────────────────────────────────

class Member(Base):
    """Junction table linking users to organisations with a role."""
    __tablename__ = "members"
    __table_args__ = (
        UniqueConstraint(
            "organisation_id", "user_id", name="uq_member_org_user"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[MemberRole] = mapped_column(
        SAEnum(MemberRole), default=MemberRole.MEMBER, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    organisation: Mapped["Organisation"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="memberships")


# ──────────────────────────────────────────
# API KEYS (Stripe-style: prefixed, hashed)
# ──────────────────────────────────────────

class ApiKey(Base):
    """API key for programmatic access. Raw key shown once on creation, only hash stored."""
    __tablename__ = "api_keys"
    __table_args__ = (
        Index("ix_api_keys_org_id", "organisation_id"),
        Index("ix_api_keys_key_hash", "key_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    environment: Mapped[KeyEnvironment] = mapped_column(
        SAEnum(KeyEnvironment), default=KeyEnvironment.LIVE
    )

    # Key storage — only hash is stored, raw key shown once
    prefix: Mapped[str] = mapped_column(String(32), nullable=False)
    key_hash: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True
    )
    last_four: Mapped[str] = mapped_column(String(4), nullable=False)

    # Permissions
    scopes: Mapped[list] = mapped_column(JSONB, default=list)
    allowed_models: Mapped[Optional[list]] = mapped_column(
        JSONB, nullable=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    organisation: Mapped["Organisation"] = relationship(back_populates="api_keys")

    @staticmethod
    def generate(environment: str = "live") -> tuple[str, str, str, str]:
        """Generate a new API key.

        Returns:
            Tuple of (raw_key, prefix, key_hash, last_four).
            raw_key is shown once to the user and never stored.
        """
        random_part = secrets.token_urlsafe(32)
        raw_key = f"asahi_{environment}_{random_part}"
        prefix = f"asahi_{environment}_{random_part[:4]}"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        last_four = random_part[-4:]
        return raw_key, prefix, key_hash, last_four


# ──────────────────────────────────────────
# REQUEST LOGS (Core metering + audit table)
# ──────────────────────────────────────────

class RequestLog(Base):
    """Per-request log for metering, analytics, and audit."""
    __tablename__ = "request_logs"
    __table_args__ = (
        Index("ix_request_logs_org_created", "organisation_id", "created_at"),
        Index("ix_request_logs_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id"), nullable=False
    )
    api_key_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("api_keys.id"), nullable=True
    )

    # Request details
    model_requested: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    routing_mode: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )

    # Token counts
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)

    # Cost tracking (the core USP)
    cost_without_asahi: Mapped[float] = mapped_column(
        Numeric(12, 8), nullable=False
    )
    cost_with_asahi: Mapped[float] = mapped_column(
        Numeric(12, 8), nullable=False
    )
    savings_usd: Mapped[float] = mapped_column(Numeric(12, 8), nullable=False)
    savings_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(6, 2), nullable=True
    )

    # Cache info
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    cache_tier: Mapped[Optional[CacheType]] = mapped_column(
        SAEnum(CacheType), nullable=True
    )
    semantic_similarity: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 4), nullable=True
    )

    # Performance
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status_code: Mapped[int] = mapped_column(Integer, default=200)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    organisation: Mapped["Organisation"] = relationship(
        back_populates="request_logs"
    )


# ──────────────────────────────────────────
# USAGE SNAPSHOTS (Pre-aggregated for dashboard speed)
# ──────────────────────────────────────────

class UsageSnapshot(Base):
    """Hourly pre-aggregated usage — avoids scanning request_logs for dashboards."""
    __tablename__ = "usage_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "organisation_id", "hour_bucket", name="uq_snapshot_org_hour"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id"), nullable=False
    )
    hour_bucket: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    total_requests: Mapped[int] = mapped_column(Integer, default=0)
    cache_hits: Mapped[int] = mapped_column(Integer, default=0)
    total_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_without_asahi: Mapped[float] = mapped_column(
        Numeric(14, 8), default=0
    )
    total_cost_with_asahi: Mapped[float] = mapped_column(
        Numeric(14, 8), default=0
    )
    total_savings_usd: Mapped[float] = mapped_column(Numeric(14, 8), default=0)
    avg_latency_ms: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    p99_latency_ms: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    organisation: Mapped["Organisation"] = relationship(
        back_populates="usage_snapshots"
    )


# ──────────────────────────────────────────
# AUDIT LOG (Immutable — governance/compliance)
# ──────────────────────────────────────────

class AuditLog(Base):
    """Immutable audit trail for governance and compliance."""
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_org_created", "organisation_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id"), nullable=False
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )
    resource_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    metadata_: Mapped[Optional[dict]] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45), nullable=True
    )
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ──────────────────────────────────────────
# INVITATIONS
# ──────────────────────────────────────────

class Invitation(Base):
    """Pending invitation to join an organisation."""
    __tablename__ = "invitations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
    )
    invited_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[MemberRole] = mapped_column(
        SAEnum(MemberRole), default=MemberRole.MEMBER
    )
    token: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True
    )
    accepted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

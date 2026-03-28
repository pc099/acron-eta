"""SQLAlchemy 2.0 ORM models for ASAHIO SaaS platform."""

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


class PlanTier(str, enum.Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class ComplianceTier(str, enum.Enum):
    STANDARD = "standard"
    ENTERPRISE = "enterprise"
    HIPAA = "hipaa"


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


class RoutingMode(str, enum.Enum):
    AUTO = "AUTO"
    EXPLICIT = "EXPLICIT"
    GUIDED = "GUIDED"


class InterventionMode(str, enum.Enum):
    OBSERVE = "OBSERVE"
    ASSISTED = "ASSISTED"
    AUTONOMOUS = "AUTONOMOUS"


class BillingStatus(str, enum.Enum):
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"


class ModelEndpointType(str, enum.Enum):
    PLATFORM = "platform"
    FINE_TUNED = "fine_tuned"
    EXTERNAL = "external"


class AgentTypeClassification(str, enum.Enum):
    """Behavioral classification of an agent's primary interaction pattern."""

    CHATBOT = "CHATBOT"
    RAG = "RAG"
    CODING = "CODING"
    WORKFLOW = "WORKFLOW"
    AUTONOMOUS = "AUTONOMOUS"


class OutputTypeClassification(str, enum.Enum):
    """Classification of a single LLM response's structural type."""

    FACTUAL = "FACTUAL"
    CREATIVE = "CREATIVE"
    CODE = "CODE"
    STRUCTURED = "STRUCTURED"
    CONVERSATIONAL = "CONVERSATIONAL"


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
    compliance_tier: Mapped[ComplianceTier] = mapped_column(
        SAEnum(ComplianceTier), default=ComplianceTier.STANDARD, nullable=False
    )

    stripe_customer_id: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, nullable=True
    )
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, nullable=True
    )

    monthly_request_limit: Mapped[int] = mapped_column(Integer, default=10_000)
    monthly_token_limit: Mapped[int] = mapped_column(Integer, default=1_000_000)
    monthly_budget_usd: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 4), nullable=True
    )

    routing_weight_overrides: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True
    )
    ip_allowlist: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    # Pinecone index name for per-org semantic cache isolation
    pinecone_index_name: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

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
    agents: Mapped[list["Agent"]] = relationship(
        back_populates="organisation", cascade="all, delete-orphan"
    )
    agent_sessions: Mapped[list["AgentSession"]] = relationship(
        back_populates="organisation", cascade="all, delete-orphan"
    )
    call_traces: Mapped[list["CallTrace"]] = relationship(
        back_populates="organisation", cascade="all, delete-orphan"
    )
    routing_decision_logs: Mapped[list["RoutingDecisionLog"]] = relationship(
        back_populates="organisation", cascade="all, delete-orphan"
    )
    model_endpoints: Mapped[list["ModelEndpoint"]] = relationship(
        back_populates="organisation", cascade="all, delete-orphan"
    )
    billing_account: Mapped[Optional["BillingAccount"]] = relationship(
        back_populates="organisation", cascade="all, delete-orphan", uselist=False
    )


class User(Base):
    """A user who can belong to multiple organisations via memberships."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    clerk_user_id: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    memberships: Mapped[list["Member"]] = relationship(back_populates="user")


class Member(Base):
    """Junction table linking users to organisations with a role."""

    __tablename__ = "members"
    __table_args__ = (
        UniqueConstraint("organisation_id", "user_id", name="uq_member_org_user"),
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


class ApiKey(Base):
    """API key for programmatic access. Raw key shown once on creation."""

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
    prefix: Mapped[str] = mapped_column(String(32), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    last_four: Mapped[str] = mapped_column(String(4), nullable=False)
    scopes: Mapped[list] = mapped_column(JSONB, default=list)
    allowed_models: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
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
        """Generate a new API key."""
        random_part = secrets.token_urlsafe(32)
        raw_key = f"asahio_{environment}_{random_part}"
        prefix = f"asahio_{environment}_{random_part[:4]}"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        last_four = random_part[-4:]
        return raw_key, prefix, key_hash, last_four


class BillingAccount(Base):
    """Billing state attached to an organisation."""

    __tablename__ = "billing_accounts"
    __table_args__ = (
        UniqueConstraint("organisation_id", name="uq_billing_account_org"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
    )
    plan: Mapped[PlanTier] = mapped_column(
        SAEnum(PlanTier), default=PlanTier.FREE, nullable=False
    )
    status: Mapped[BillingStatus] = mapped_column(
        SAEnum(BillingStatus), default=BillingStatus.TRIALING, nullable=False
    )
    billing_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    stripe_price_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    stripe_meter_name: Mapped[str] = mapped_column(
        String(255), default="asahio_tokens", nullable=False
    )
    current_period_start: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_period_end: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    organisation: Mapped["Organisation"] = relationship(back_populates="billing_account")


class ModelEndpoint(Base):
    """Registered BYOM endpoint or pinned model configuration."""

    __tablename__ = "model_endpoints"
    __table_args__ = (Index("ix_model_endpoints_org_id", "organisation_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    endpoint_type: Mapped[ModelEndpointType] = mapped_column(
        SAEnum(ModelEndpointType), default=ModelEndpointType.PLATFORM, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(100), nullable=False, default="asahio")
    model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    endpoint_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    secret_reference: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    default_headers: Mapped[Optional[dict]] = mapped_column("default_headers", JSONB, default=dict)
    capability_flags: Mapped[Optional[dict]] = mapped_column("capability_flags", JSONB, default=dict)
    fallback_model_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    health_status: Mapped[str] = mapped_column(String(50), default="unknown", nullable=False)
    last_health_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    organisation: Mapped["Organisation"] = relationship(back_populates="model_endpoints")
    agents: Mapped[list["Agent"]] = relationship(back_populates="model_endpoint")


class Agent(Base):
    """First-class agent configuration owned by an organisation."""

    __tablename__ = "agents"
    __table_args__ = (
        Index("ix_agents_org_id", "organisation_id"),
        UniqueConstraint("organisation_id", "slug", name="uq_agents_org_slug"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
    )
    model_endpoint_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_endpoints.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    routing_mode: Mapped[RoutingMode] = mapped_column(
        SAEnum(RoutingMode), default=RoutingMode.AUTO, nullable=False
    )
    intervention_mode: Mapped[InterventionMode] = mapped_column(
        SAEnum(InterventionMode), default=InterventionMode.OBSERVE, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)
    mode_entered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    autonomous_authorized_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    autonomous_authorized_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    risk_threshold_overrides: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    organisation: Mapped["Organisation"] = relationship(back_populates="agents")
    model_endpoint: Mapped[Optional["ModelEndpoint"]] = relationship(back_populates="agents")
    sessions: Mapped[list["AgentSession"]] = relationship(
        back_populates="agent", cascade="all, delete-orphan"
    )
    call_traces: Mapped[list["CallTrace"]] = relationship(back_populates="agent")
    routing_decision_logs: Mapped[list["RoutingDecisionLog"]] = relationship(
        back_populates="agent"
    )


class AgentSession(Base):
    """Tracks a logical session for an agent across calls."""

    __tablename__ = "agent_sessions"
    __table_args__ = (
        Index("ix_agent_sessions_org_id", "organisation_id"),
        UniqueConstraint(
            "organisation_id",
            "agent_id",
            "external_session_id",
            name="uq_agent_sessions_external",
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
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    external_session_id: Mapped[str] = mapped_column(String(255), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    organisation: Mapped["Organisation"] = relationship(back_populates="agent_sessions")
    agent: Mapped["Agent"] = relationship(back_populates="sessions")
    call_traces: Mapped[list["CallTrace"]] = relationship(back_populates="agent_session")


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
    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=True
    )
    agent_session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_sessions.id"), nullable=True
    )
    model_endpoint_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_endpoints.id"), nullable=True
    )
    request_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    model_requested: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    routing_mode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    intervention_mode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)

    cost_without_asahi: Mapped[float] = mapped_column(Numeric(12, 8), nullable=False)
    cost_with_asahi: Mapped[float] = mapped_column(Numeric(12, 8), nullable=False)
    savings_usd: Mapped[float] = mapped_column(Numeric(12, 8), nullable=False)
    savings_pct: Mapped[Optional[float]] = mapped_column(Numeric(6, 2), nullable=True)

    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    cache_tier: Mapped[Optional[CacheType]] = mapped_column(SAEnum(CacheType), nullable=True)
    semantic_similarity: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)

    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status_code: Mapped[int] = mapped_column(Integer, default=200)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    organisation: Mapped["Organisation"] = relationship(back_populates="request_logs")


class CallTrace(Base):
    """Detailed per-call trace powering agent analytics and future ABA."""

    __tablename__ = "call_traces"
    __table_args__ = (
        Index("ix_call_traces_org_created", "organisation_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=True
    )
    agent_session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_sessions.id"), nullable=True
    )
    request_log_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("request_logs.id"), nullable=True
    )
    request_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    model_requested: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    model_used: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    routing_mode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    intervention_mode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    policy_action: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    policy_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    cache_tier: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    trace_metadata: Mapped[Optional[dict]] = mapped_column("trace_metadata", JSONB, default=dict)
    risk_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)
    intervention_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    hallucination_tag: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    hallucination_tag_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # SDK v2 tool support fields
    tools_requested: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    tools_called: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    tool_call_count: Mapped[int] = mapped_column(Integer, default=0)
    web_search_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mcp_servers_used: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    computer_use_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    chain_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("guided_chains.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    organisation: Mapped["Organisation"] = relationship(back_populates="call_traces")
    agent: Mapped[Optional["Agent"]] = relationship(back_populates="call_traces")
    agent_session: Mapped[Optional["AgentSession"]] = relationship(back_populates="call_traces")


class RoutingDecisionLog(Base):
    """Explains how a call was routed for auditability and operator review."""

    __tablename__ = "routing_decision_logs"
    __table_args__ = (
        Index("ix_routing_decisions_org_created", "organisation_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=True
    )
    call_trace_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("call_traces.id"), nullable=True
    )
    routing_mode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    intervention_mode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    selected_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    selected_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)
    decision_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    factors: Mapped[Optional[dict]] = mapped_column("factors", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    organisation: Mapped["Organisation"] = relationship(back_populates="routing_decision_logs")
    agent: Mapped[Optional["Agent"]] = relationship(back_populates="routing_decision_logs")


class UsageSnapshot(Base):
    """Hourly pre-aggregated usage for dashboard performance."""

    __tablename__ = "usage_snapshots"
    __table_args__ = (
        UniqueConstraint("organisation_id", "hour_bucket", name="uq_snapshot_org_hour"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id"), nullable=False
    )
    hour_bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_requests: Mapped[int] = mapped_column(Integer, default=0)
    cache_hits: Mapped[int] = mapped_column(Integer, default=0)
    total_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_without_asahi: Mapped[float] = mapped_column(Numeric(14, 8), default=0)
    total_cost_with_asahi: Mapped[float] = mapped_column(Numeric(14, 8), default=0)
    total_savings_usd: Mapped[float] = mapped_column(Numeric(14, 8), default=0)
    avg_latency_ms: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    p99_latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    organisation: Mapped["Organisation"] = relationship(back_populates="usage_snapshots")


class AuditLog(Base):
    """Immutable audit trail for governance and compliance."""

    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_org_created", "organisation_id", "created_at"),)

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
    resource_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RoutingConstraint(Base):
    """Persisted routing rule for GUIDED mode, scoped to org or agent."""

    __tablename__ = "routing_constraints"
    __table_args__ = (
        Index("ix_routing_constraints_org_id", "organisation_id"),
        Index("ix_routing_constraints_agent_id", "agent_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=True
    )
    rule_type: Mapped[str] = mapped_column(String(50), nullable=False)
    rule_config: Mapped[dict] = mapped_column("rule_config", JSONB, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    organisation: Mapped["Organisation"] = relationship("Organisation")
    agent: Mapped[Optional["Agent"]] = relationship("Agent")


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
    token: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AgentFingerprint(Base):
    """Behavioral fingerprint for an agent, updated incrementally via EMA."""

    __tablename__ = "agent_fingerprints"
    __table_args__ = (
        Index("ix_agent_fingerprints_org_id", "organisation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
    )
    total_observations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_complexity: Mapped[float] = mapped_column(Numeric(5, 4), default=0.0, nullable=False)
    avg_context_length: Mapped[float] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)
    hallucination_rate: Mapped[float] = mapped_column(Numeric(5, 4), default=0.0, nullable=False)
    model_distribution: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    cache_hit_rate: Mapped[float] = mapped_column(Numeric(5, 4), default=0.0, nullable=False)
    baseline_confidence: Mapped[float] = mapped_column(Numeric(5, 4), default=0.0, nullable=False)
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    agent: Mapped["Agent"] = relationship("Agent", backref="fingerprint", uselist=False)
    organisation: Mapped["Organisation"] = relationship("Organisation")


class StructuralRecord(Base):
    """Per-call structural analysis record for ABA behavioral analytics."""

    __tablename__ = "structural_records"
    __table_args__ = (
        Index("ix_structural_records_org_agent", "organisation_id", "agent_id"),
        Index("ix_structural_records_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
    )
    call_trace_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("call_traces.id"), nullable=True
    )
    query_complexity_score: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    agent_type_classification: Mapped[AgentTypeClassification] = mapped_column(
        SAEnum(AgentTypeClassification), nullable=False
    )
    output_type_classification: Mapped[OutputTypeClassification] = mapped_column(
        SAEnum(OutputTypeClassification), nullable=False
    )
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    hallucination_detected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    agent: Mapped["Agent"] = relationship("Agent")
    organisation: Mapped["Organisation"] = relationship("Organisation")


class InterventionLog(Base):
    """Immutable record of every intervention decision on the gateway path."""

    __tablename__ = "intervention_logs"
    __table_args__ = (
        Index("ix_intervention_logs_org_created", "organisation_id", "created_at"),
        Index("ix_intervention_logs_agent_id", "agent_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
    )
    call_trace_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("call_traces.id", ondelete="SET NULL"),
        nullable=True,
    )
    request_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    intervention_level: Mapped[int] = mapped_column(Integer, nullable=False)
    intervention_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    risk_score: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    risk_factors: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    action_taken: Mapped[str] = mapped_column(String(50), nullable=False)
    action_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    original_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    final_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    prompt_modified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    was_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    organisation: Mapped["Organisation"] = relationship("Organisation")
    agent: Mapped[Optional["Agent"]] = relationship("Agent")


class ModeTransitionLog(Base):
    """Audit trail for agent intervention mode transitions."""

    __tablename__ = "mode_transition_logs"
    __table_args__ = (
        Index("ix_mode_transitions_org_agent", "organisation_id", "agent_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    previous_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    new_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    trigger: Mapped[str] = mapped_column(String(50), nullable=False)
    baseline_confidence: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 4), nullable=True
    )
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    operator_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    organisation: Mapped["Organisation"] = relationship("Organisation")
    agent: Mapped["Agent"] = relationship("Agent")


# ── Provider Sprint Tables ──────────────────────────────────────────────


class ProviderKey(Base):
    """BYOK (Bring Your Own Key) — encrypted API key per provider per org."""

    __tablename__ = "provider_keys"
    __table_args__ = (
        UniqueConstraint("organisation_id", "provider", name="uq_provider_key_org_provider"),
        Index("ix_provider_keys_org_id", "organisation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    encrypted_key: Mapped[str] = mapped_column(Text, nullable=False)
    key_hint: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    organisation: Mapped["Organisation"] = relationship("Organisation")


class GuidedChain(Base):
    """Customer-defined fallback chain for GUIDED routing mode."""

    __tablename__ = "guided_chains"
    __table_args__ = (
        Index("ix_guided_chains_org_id", "organisation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    fallback_triggers: Mapped[list] = mapped_column(
        JSONB, default=lambda: ["rate_limit", "server_error", "timeout"], nullable=False
    )
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    organisation: Mapped["Organisation"] = relationship("Organisation")
    slots: Mapped[list["ChainSlot"]] = relationship(
        "ChainSlot", back_populates="chain", cascade="all, delete-orphan",
        order_by="ChainSlot.priority",
    )


class ChainSlot(Base):
    """One slot (primary or fallback) in a guided chain."""

    __tablename__ = "chain_slots"
    __table_args__ = (
        UniqueConstraint("chain_id", "priority", name="uq_chain_slot_position"),
        Index("ix_chain_slots_chain_id", "chain_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    chain_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("guided_chains.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    max_latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_cost_per_1k_tokens: Mapped[Optional[float]] = mapped_column(
        Numeric(8, 6), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    chain: Mapped["GuidedChain"] = relationship("GuidedChain", back_populates="slots")


class OllamaConfig(Base):
    """Customer's self-hosted Ollama instance configuration."""

    __tablename__ = "ollama_configs"
    __table_args__ = (
        UniqueConstraint("organisation_id", "base_url", name="uq_ollama_config_org_url"),
        Index("ix_ollama_configs_org_id", "organisation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    available_models: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    organisation: Mapped["Organisation"] = relationship("Organisation")

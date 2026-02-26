"""Initial schema — organisations, users, members, API keys, request logs,
usage snapshots, audit logs, invitations.

Revision ID: 001
Revises: None
Create Date: 2026-02-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Enum types
plan_tier = postgresql.ENUM("free", "pro", "enterprise", name="plantier", create_type=False)
member_role = postgresql.ENUM("owner", "admin", "member", "viewer", name="memberrole", create_type=False)
key_environment = postgresql.ENUM("live", "test", name="keyenvironment", create_type=False)
cache_type = postgresql.ENUM("exact", "semantic", "intermediate", "miss", name="cachetype", create_type=False)


def upgrade() -> None:
    # Create enum types
    plan_tier.create(op.get_bind(), checkfirst=True)
    member_role.create(op.get_bind(), checkfirst=True)
    key_environment.create(op.get_bind(), checkfirst=True)
    cache_type.create(op.get_bind(), checkfirst=True)

    # Organisations
    op.create_table(
        "organisations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False, unique=True),
        sa.Column("plan", plan_tier, nullable=False, server_default="free"),
        sa.Column("stripe_customer_id", sa.String(255), unique=True, nullable=True),
        sa.Column("stripe_subscription_id", sa.String(255), unique=True, nullable=True),
        sa.Column("monthly_request_limit", sa.Integer, server_default="10000"),
        sa.Column("monthly_token_limit", sa.Integer, server_default="1000000"),
        sa.Column("monthly_budget_usd", sa.Numeric(12, 4), nullable=True),
        sa.Column("metadata", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("avatar_url", sa.Text, nullable=True),
        sa.Column("clerk_user_id", sa.String(255), unique=True, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Members
    op.create_table(
        "members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organisation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organisations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", member_role, nullable=False, server_default="member"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("organisation_id", "user_id", name="uq_member_org_user"),
    )

    # API Keys
    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organisation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organisations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("environment", key_environment, server_default="live"),
        sa.Column("prefix", sa.String(32), nullable=False),
        sa.Column("key_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("last_four", sa.String(4), nullable=False),
        sa.Column("scopes", postgresql.JSONB, server_default="[]"),
        sa.Column("allowed_models", postgresql.JSONB, nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_api_keys_org_id", "api_keys", ["organisation_id"])
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])

    # Request Logs
    op.create_table(
        "request_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organisation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organisations.id"),
            nullable=False,
        ),
        sa.Column(
            "api_key_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("api_keys.id"),
            nullable=True,
        ),
        sa.Column("model_requested", sa.String(100), nullable=True),
        sa.Column("model_used", sa.String(100), nullable=False),
        sa.Column("provider", sa.String(50), nullable=True),
        sa.Column("routing_mode", sa.String(20), nullable=True),
        sa.Column("input_tokens", sa.Integer, server_default="0"),
        sa.Column("output_tokens", sa.Integer, server_default="0"),
        sa.Column("cost_without_asahi", sa.Numeric(12, 8), nullable=False),
        sa.Column("cost_with_asahi", sa.Numeric(12, 8), nullable=False),
        sa.Column("savings_usd", sa.Numeric(12, 8), nullable=False),
        sa.Column("savings_pct", sa.Numeric(6, 2), nullable=True),
        sa.Column("cache_hit", sa.Boolean, server_default="false"),
        sa.Column("cache_tier", cache_type, nullable=True),
        sa.Column("semantic_similarity", sa.Numeric(5, 4), nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("status_code", sa.Integer, server_default="200"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_request_logs_org_created", "request_logs", ["organisation_id", "created_at"])
    op.create_index("ix_request_logs_created_at", "request_logs", ["created_at"])

    # Usage Snapshots
    op.create_table(
        "usage_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organisation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organisations.id"),
            nullable=False,
        ),
        sa.Column("hour_bucket", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_requests", sa.Integer, server_default="0"),
        sa.Column("cache_hits", sa.Integer, server_default="0"),
        sa.Column("total_input_tokens", sa.Integer, server_default="0"),
        sa.Column("total_output_tokens", sa.Integer, server_default="0"),
        sa.Column("total_cost_without_asahi", sa.Numeric(14, 8), server_default="0"),
        sa.Column("total_cost_with_asahi", sa.Numeric(14, 8), server_default="0"),
        sa.Column("total_savings_usd", sa.Numeric(14, 8), server_default="0"),
        sa.Column("avg_latency_ms", sa.Numeric(10, 2), nullable=True),
        sa.Column("p99_latency_ms", sa.Integer, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("organisation_id", "hour_bucket", name="uq_snapshot_org_hour"),
    )

    # Audit Logs
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organisation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organisations.id"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=True),
        sa.Column("resource_id", sa.String(255), nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_audit_logs_org_created", "audit_logs", ["organisation_id", "created_at"])

    # Invitations
    op.create_table(
        "invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organisation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organisations.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "invited_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", member_role, server_default="member"),
        sa.Column("token", sa.String(128), nullable=False, unique=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("invitations")
    op.drop_table("audit_logs")
    op.drop_table("usage_snapshots")
    op.drop_table("request_logs")
    op.drop_table("api_keys")
    op.drop_table("members")
    op.drop_table("users")
    op.drop_table("organisations")

    # Drop enum types
    cache_type.drop(op.get_bind(), checkfirst=True)
    key_environment.drop(op.get_bind(), checkfirst=True)
    member_role.drop(op.get_bind(), checkfirst=True)
    plan_tier.drop(op.get_bind(), checkfirst=True)

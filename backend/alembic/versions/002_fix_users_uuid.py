"""Fix users.id to UUID when it was created as integer.

Drops tables that reference users, then recreates users (and dependents) with UUID.
Run this if you see: foreign key constraint members_user_id_fkey cannot be implemented
(Key columns user_id and id are of incompatible types: uuid and integer).

Revision ID: 002
Revises: 001
Create Date: 2026-02-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Reuse enum types from 001 (they must already exist)
plan_tier = postgresql.ENUM(
    "free", "pro", "enterprise", name="plantier", create_type=False
)
member_role = postgresql.ENUM(
    "owner", "admin", "member", "viewer", name="memberrole", create_type=False
)
key_environment = postgresql.ENUM(
    "live", "test", name="keyenvironment", create_type=False
)
cache_type = postgresql.ENUM(
    "exact", "semantic", "intermediate", "miss", name="cachetype", create_type=False
)


def _recreate_users(bind) -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("avatar_url", sa.Text, nullable=True),
        sa.Column("clerk_user_id", sa.String(255), unique=True, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )


def _recreate_members(bind) -> None:
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
        sa.Column(
            "role", member_role, nullable=False, server_default="member"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "organisation_id", "user_id", name="uq_member_org_user"
        ),
    )


def _recreate_api_keys(bind) -> None:
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
        sa.Column(
            "environment", key_environment, server_default="live"
        ),
        sa.Column("prefix", sa.String(32), nullable=False),
        sa.Column(
            "key_hash", sa.String(128), nullable=False, unique=True
        ),
        sa.Column("last_four", sa.String(4), nullable=False),
        sa.Column("scopes", postgresql.JSONB, server_default="[]"),
        sa.Column("allowed_models", postgresql.JSONB, nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column(
            "last_used_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_api_keys_org_id", "api_keys", ["organisation_id"])
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])


def _recreate_request_logs(bind) -> None:
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
        sa.Column(
            "cost_without_asahi", sa.Numeric(12, 8), nullable=False
        ),
        sa.Column("cost_with_asahi", sa.Numeric(12, 8), nullable=False),
        sa.Column("savings_usd", sa.Numeric(12, 8), nullable=False),
        sa.Column("savings_pct", sa.Numeric(6, 2), nullable=True),
        sa.Column("cache_hit", sa.Boolean, server_default="false"),
        sa.Column("cache_tier", cache_type, nullable=True),
        sa.Column(
            "semantic_similarity", sa.Numeric(5, 4), nullable=True
        ),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("status_code", sa.Integer, server_default="200"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_request_logs_org_created",
        "request_logs",
        ["organisation_id", "created_at"],
    )
    op.create_index("ix_request_logs_created_at", "request_logs", ["created_at"])


def _recreate_audit_logs(bind) -> None:
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
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_audit_logs_org_created",
        "audit_logs",
        ["organisation_id", "created_at"],
    )


def _recreate_invitations(bind) -> None:
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
        sa.Column(
            "accepted_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "expires_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )


def upgrade() -> None:
    bind = op.get_bind()
    # Check if users table exists and users.id is integer (wrong schema)
    result = bind.execute(
        sa.text(
            """
        SELECT data_type FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'id'
        """
        )
    )
    row = result.fetchone()
    if row and row[0] != "uuid":
        # Drop tables that depend on users (order matters for FKs).
        # Use IF EXISTS in case create_all() failed before creating some tables.
        for table in (
            "invitations",
            "audit_logs",
            "request_logs",
            "api_keys",
            "members",
            "users",
        ):
            bind.execute(sa.text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))
        _recreate_users(bind)
        _recreate_members(bind)
        _recreate_api_keys(bind)
        _recreate_request_logs(bind)
        _recreate_audit_logs(bind)
        _recreate_invitations(bind)


def downgrade() -> None:
    # This migration is a one-way fix; downgrade is a no-op
    # (reverting would require restoring integer users.id, which we don't want)
    pass

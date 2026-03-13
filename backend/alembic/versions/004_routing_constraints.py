"""Add routing_constraints table for persisted GUIDED mode rules.

Revision ID: 004_routing_constraints
Revises: 003_phase1
Create Date: 2026-03-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004_routing_constraints"
down_revision: Union[str, None] = "003_phase1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "routing_constraints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organisation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organisations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("rule_type", sa.String(50), nullable=False),
        sa.Column("rule_config", postgresql.JSONB, nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_routing_constraints_org_id", "routing_constraints", ["organisation_id"])
    op.create_index("ix_routing_constraints_agent_id", "routing_constraints", ["agent_id"])


def downgrade() -> None:
    op.drop_index("ix_routing_constraints_agent_id", table_name="routing_constraints")
    op.drop_index("ix_routing_constraints_org_id", table_name="routing_constraints")
    op.drop_table("routing_constraints")

"""Add agent_fingerprints and structural_records tables for ABA engine.

Revision ID: 006_aba_tables
Revises: 005_immutable_audit
Create Date: 2026-03-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006_aba_tables"
down_revision: Union[str, None] = "005_immutable_audit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Enum type names
AGENT_TYPE_ENUM = "agenttypeclassification"
OUTPUT_TYPE_ENUM = "outputtypeclassification"


def _table_exists(bind, table_name: str) -> bool:
    """Check if a table exists in the public schema."""
    result = bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = :t"
        ),
        {"t": table_name},
    )
    return result.scalar() is not None


def upgrade() -> None:
    bind = op.get_bind()

    # Create enum types idempotently using PL/pgSQL exception handling.
    # checkfirst=True does not work reliably with asyncpg on Railway.
    if bind.dialect.name == "postgresql":
        op.execute(sa.text(
            "DO $$ BEGIN "
            "CREATE TYPE agenttypeclassification AS ENUM "
            "('CHATBOT','RAG','CODING','WORKFLOW','AUTONOMOUS'); "
            "EXCEPTION WHEN duplicate_object THEN null; "
            "END $$;"
        ))
        op.execute(sa.text(
            "DO $$ BEGIN "
            "CREATE TYPE outputtypeclassification AS ENUM "
            "('FACTUAL','CREATIVE','CODE','STRUCTURED','CONVERSATIONAL'); "
            "EXCEPTION WHEN duplicate_object THEN null; "
            "END $$;"
        ))

    # Guard table creation against partial prior runs.
    if not _table_exists(bind, "agent_fingerprints"):
        op.create_table(
            "agent_fingerprints",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "agent_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("agents.id", ondelete="CASCADE"),
                nullable=False,
                unique=True,
            ),
            sa.Column(
                "organisation_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("organisations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("total_observations", sa.Integer, nullable=False, server_default="0"),
            sa.Column("avg_complexity", sa.Numeric(5, 4), nullable=False, server_default="0"),
            sa.Column("avg_context_length", sa.Numeric(10, 2), nullable=False, server_default="0"),
            sa.Column("hallucination_rate", sa.Numeric(5, 4), nullable=False, server_default="0"),
            sa.Column("model_distribution", postgresql.JSONB, nullable=False, server_default="{}"),
            sa.Column("cache_hit_rate", sa.Numeric(5, 4), nullable=False, server_default="0"),
            sa.Column("baseline_confidence", sa.Numeric(5, 4), nullable=False, server_default="0"),
            sa.Column("last_updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_agent_fingerprints_org_id", "agent_fingerprints", ["organisation_id"])

    if not _table_exists(bind, "structural_records"):
        op.create_table(
            "structural_records",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "agent_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("agents.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "organisation_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("organisations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "call_trace_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("call_traces.id"),
                nullable=True,
            ),
            sa.Column("query_complexity_score", sa.Numeric(5, 4), nullable=False),
            sa.Column("agent_type_classification", postgresql.ENUM(
                "CHATBOT", "RAG", "CODING", "WORKFLOW", "AUTONOMOUS",
                name=AGENT_TYPE_ENUM, create_type=False,
            ), nullable=False),
            sa.Column("output_type_classification", postgresql.ENUM(
                "FACTUAL", "CREATIVE", "CODE", "STRUCTURED", "CONVERSATIONAL",
                name=OUTPUT_TYPE_ENUM, create_type=False,
            ), nullable=False),
            sa.Column("token_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("latency_ms", sa.Integer, nullable=True),
            sa.Column("model_used", sa.String(100), nullable=False),
            sa.Column("cache_hit", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("hallucination_detected", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_structural_records_org_agent", "structural_records", ["organisation_id", "agent_id"])
        op.create_index("ix_structural_records_created_at", "structural_records", ["created_at"])


def downgrade() -> None:
    op.drop_table("structural_records")
    op.drop_table("agent_fingerprints")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(f"DROP TYPE IF EXISTS {OUTPUT_TYPE_ENUM}")
        op.execute(f"DROP TYPE IF EXISTS {AGENT_TYPE_ENUM}")

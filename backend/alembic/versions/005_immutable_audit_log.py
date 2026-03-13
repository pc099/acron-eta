"""Add immutability triggers to audit_logs table.

Prevents UPDATE and DELETE operations at the database level,
ensuring audit entries can never be tampered with.

Revision ID: 005_immutable_audit
Revises: 004_routing_constraints
Create Date: 2026-03-13
"""

from typing import Sequence, Union

from alembic import op

revision: str = "005_immutable_audit"
down_revision: Union[str, None] = "004_routing_constraints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Only apply triggers on PostgreSQL — SQLite doesn't support this syntax
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_audit_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs table is immutable — updates and deletes are forbidden';
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER no_audit_update
        BEFORE UPDATE ON audit_logs
        FOR EACH ROW
        EXECUTE FUNCTION prevent_audit_mutation();
    """)

    op.execute("""
        CREATE TRIGGER no_audit_delete
        BEFORE DELETE ON audit_logs
        FOR EACH ROW
        EXECUTE FUNCTION prevent_audit_mutation();
    """)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("DROP TRIGGER IF EXISTS no_audit_delete ON audit_logs;")
    op.execute("DROP TRIGGER IF EXISTS no_audit_update ON audit_logs;")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_mutation();")

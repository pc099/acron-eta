"""Per-org Pinecone indexes

Revision ID: 011_per_org_pinecone_indexes
Revises: 010_sdk_v2_tool_support
Create Date: 2026-03-27

Adds pinecone_index_name column to organisations table to support
per-org semantic cache isolation with dedicated Pinecone indexes.

This enables true data isolation where each org has its own Pinecone
index instead of relying on metadata filtering on a shared index.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "011_per_org_pinecone_indexes"
down_revision: Union[str, None] = "010_sdk_v2_tool_support"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add pinecone_index_name to organisations table."""
    op.add_column(
        "organisations",
        sa.Column("pinecone_index_name", sa.String(255), nullable=True),
    )

    # Backfill existing orgs with the shared index name (for backward compatibility)
    # This allows gradual migration without breaking existing functionality
    op.execute(
        "UPDATE organisations SET pinecone_index_name = 'asahio-semantic-cache' WHERE pinecone_index_name IS NULL"
    )

    # Add index for faster lookups by Pinecone index name
    op.create_index(
        "ix_organisations_pinecone_index",
        "organisations",
        ["pinecone_index_name"],
    )


def downgrade() -> None:
    """Remove pinecone_index_name from organisations table."""
    op.drop_index("ix_organisations_pinecone_index", table_name="organisations")
    op.drop_column("organisations", "pinecone_index_name")

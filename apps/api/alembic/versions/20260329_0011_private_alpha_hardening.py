"""Add private alpha auth ownership and audit metadata fields.

Revision ID: 20260329_0011
Revises: 20260324_0010
Create Date: 2026-03-29
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260329_0011"
down_revision = "20260324_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("owner_username", sa.String(length=255), nullable=True))
    op.add_column("projects", sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("projects", sa.Column("purged_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.execute("UPDATE projects SET owner_username = 'local-dev' WHERE owner_username IS NULL;")
    op.alter_column("projects", "owner_username", nullable=False)
    op.create_index("projects_owner_status_updated_idx", "projects", ["owner_username", "status", "updated_at"])
    op.create_index("projects_deleted_purge_idx", "projects", ["status", "deleted_at", "purged_at"])

    op.add_column("audit_events", sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("audit_events", "metadata_json")
    op.drop_index("projects_deleted_purge_idx", table_name="projects")
    op.drop_index("projects_owner_status_updated_idx", table_name="projects")
    op.drop_column("projects", "purged_at")
    op.drop_column("projects", "deleted_at")
    op.drop_column("projects", "owner_username")

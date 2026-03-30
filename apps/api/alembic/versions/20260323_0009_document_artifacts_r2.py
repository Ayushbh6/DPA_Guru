"""Add document artifact ledger for object storage-backed document persistence.

Revision ID: 20260323_0009
Revises: 20260322_0008
Create Date: 2026-03-23
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260323_0009"
down_revision = "20260322_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("artifact_type", sa.String(length=64), nullable=False),
        sa.Column("storage_provider", sa.String(length=32), nullable=False),
        sa.Column("bucket", sa.String(length=255), nullable=True),
        sa.Column("object_key", sa.String(length=1024), nullable=False),
        sa.Column("object_uri", sa.String(length=1024), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("created_by_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("document_parse_jobs.id"), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "document_artifacts_document_type_created_idx",
        "document_artifacts",
        ["document_id", "artifact_type", "created_at"],
    )
    op.create_index(
        "document_artifacts_tenant_created_idx",
        "document_artifacts",
        ["tenant_id", "created_at"],
    )

    op.execute("ALTER TABLE document_artifacts ENABLE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY document_artifacts_tenant_isolation ON document_artifacts
        FOR ALL TO PUBLIC
        USING (tenant_id = app.current_tenant_id())
        WITH CHECK (tenant_id = app.current_tenant_id());
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS document_artifacts_tenant_isolation ON document_artifacts;")
    op.drop_index("document_artifacts_tenant_created_idx", table_name="document_artifacts")
    op.drop_index("document_artifacts_document_type_created_idx", table_name="document_artifacts")
    op.drop_table("document_artifacts")

"""Upload parse jobs and document parse metadata for V1 upload-to-parse flow.

Revision ID: 20260223_0004
Revises: 20260223_0002
Create Date: 2026-02-23
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260223_0004"
down_revision = "20260223_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("parse_status", sa.String(length=32), nullable=True))
    op.add_column("documents", sa.Column("parser_route", sa.String(length=128), nullable=True))
    op.add_column("documents", sa.Column("pdf_classification", sa.String(length=32), nullable=True))
    op.add_column("documents", sa.Column("token_count_estimate", sa.Integer(), nullable=True))
    op.add_column("documents", sa.Column("extracted_text_uri", sa.String(length=1024), nullable=True))
    op.add_column("documents", sa.Column("extracted_text_format", sa.String(length=64), nullable=True))
    op.add_column("documents", sa.Column("parse_completed_at", sa.TIMESTAMP(timezone=True), nullable=True))

    op.create_table(
        "document_parse_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("progress_pct", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("file_type", sa.String(length=32), nullable=False),
        sa.Column("pdf_classification", sa.String(length=32), nullable=True),
        sa.Column("parser_route", sa.String(length=128), nullable=True),
        sa.Column("fallback_used", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("token_count_estimate", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("meta_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    op.create_check_constraint(
        "document_parse_jobs_status_check",
        "document_parse_jobs",
        "status IN ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED')",
    )
    op.create_check_constraint(
        "document_parse_jobs_pdf_classification_check",
        "document_parse_jobs",
        "pdf_classification IS NULL OR pdf_classification IN ('native', 'scanned', 'mixed')",
    )
    op.create_index(
        "document_parse_jobs_tenant_created_idx",
        "document_parse_jobs",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "document_parse_jobs_document_created_idx",
        "document_parse_jobs",
        ["document_id", "created_at"],
    )
    op.create_index(
        "document_parse_jobs_status_updated_idx",
        "document_parse_jobs",
        ["status", "updated_at"],
    )

    op.execute("ALTER TABLE document_parse_jobs ENABLE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY document_parse_jobs_tenant_isolation ON document_parse_jobs
        FOR ALL TO authenticated
        USING (tenant_id = app.current_tenant_id())
        WITH CHECK (tenant_id = app.current_tenant_id());
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS document_parse_jobs_tenant_isolation ON document_parse_jobs;")
    op.drop_index("document_parse_jobs_status_updated_idx", table_name="document_parse_jobs")
    op.drop_index("document_parse_jobs_document_created_idx", table_name="document_parse_jobs")
    op.drop_index("document_parse_jobs_tenant_created_idx", table_name="document_parse_jobs")
    op.drop_constraint("document_parse_jobs_pdf_classification_check", "document_parse_jobs", type_="check")
    op.drop_constraint("document_parse_jobs_status_check", "document_parse_jobs", type_="check")
    op.drop_table("document_parse_jobs")

    op.drop_column("documents", "parse_completed_at")
    op.drop_column("documents", "extracted_text_format")
    op.drop_column("documents", "extracted_text_uri")
    op.drop_column("documents", "token_count_estimate")
    op.drop_column("documents", "pdf_classification")
    op.drop_column("documents", "parser_route")
    op.drop_column("documents", "parse_status")

"""Checklist draft generation jobs for DPA review setup.

Revision ID: 20260322_0005
Revises: 20260223_0004
Create Date: 2026-03-22
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260322_0005"
down_revision = "20260223_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "checklist_draft_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("progress_pct", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("selected_source_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("user_instruction", sa.Text(), nullable=True),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    op.create_check_constraint(
        "checklist_draft_jobs_status_check",
        "checklist_draft_jobs",
        "status IN ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED')",
    )
    op.create_index(
        "checklist_draft_jobs_tenant_created_idx",
        "checklist_draft_jobs",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "checklist_draft_jobs_document_created_idx",
        "checklist_draft_jobs",
        ["document_id", "created_at"],
    )
    op.create_index(
        "checklist_draft_jobs_status_updated_idx",
        "checklist_draft_jobs",
        ["status", "updated_at"],
    )

    op.execute("ALTER TABLE checklist_draft_jobs ENABLE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY checklist_draft_jobs_tenant_isolation ON checklist_draft_jobs
        FOR ALL TO authenticated
        USING (tenant_id = app.current_tenant_id())
        WITH CHECK (tenant_id = app.current_tenant_id());
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS checklist_draft_jobs_tenant_isolation ON checklist_draft_jobs;")
    op.drop_index("checklist_draft_jobs_status_updated_idx", table_name="checklist_draft_jobs")
    op.drop_index("checklist_draft_jobs_document_created_idx", table_name="checklist_draft_jobs")
    op.drop_index("checklist_draft_jobs_tenant_created_idx", table_name="checklist_draft_jobs")
    op.drop_constraint("checklist_draft_jobs_status_check", "checklist_draft_jobs", type_="check")
    op.drop_table("checklist_draft_jobs")

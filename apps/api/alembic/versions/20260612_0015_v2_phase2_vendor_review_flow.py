"""Add V2 phase 2 vendor review flow fields.

Revision ID: 20260612_0015
Revises: 20260612_0014
Create Date: 2026-06-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260612_0015"
down_revision = "20260612_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("lifecycle_status", sa.String(length=32), nullable=False, server_default="active"))
    op.add_column("documents", sa.Column("archived_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("archive_expires_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("hard_deleted_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.create_check_constraint(
        "documents_lifecycle_status_check",
        "documents",
        "lifecycle_status IN ('active', 'archived', 'deleted')",
    )
    op.create_index("documents_project_lifecycle_idx", "documents", ["project_id", "lifecycle_status", "uploaded_at"])
    op.create_index("documents_archive_expires_idx", "documents", ["archive_expires_at"])
    op.drop_index("documents_project_active_primary_uidx", table_name="documents")
    op.execute(
        """
        CREATE UNIQUE INDEX documents_project_active_primary_uidx
        ON documents (project_id)
        WHERE is_primary = true
          AND active = true
          AND lifecycle_status = 'active'
          AND deleted_at IS NULL
          AND hard_deleted_at IS NULL;
        """
    )

    stale_columns = (
        ("checklist_draft_jobs", "checklist_draft_jobs_stale_document_ids_default"),
        ("approved_checklists", "approved_checklists_stale_document_ids_default"),
        ("analysis_runs", "analysis_runs_stale_document_ids_default"),
        ("analysis_reports", "analysis_reports_stale_document_ids_default"),
        ("approval_packs", "approval_packs_stale_document_ids_default"),
    )
    for table_name, _ in stale_columns:
        op.add_column(table_name, sa.Column("stale_at", sa.TIMESTAMP(timezone=True), nullable=True))
        op.add_column(table_name, sa.Column("stale_reason", sa.Text(), nullable=True))
        op.add_column(
            table_name,
            sa.Column(
                "stale_document_ids",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
        )


def downgrade() -> None:
    for table_name in (
        "approval_packs",
        "analysis_reports",
        "analysis_runs",
        "approved_checklists",
        "checklist_draft_jobs",
    ):
        op.drop_column(table_name, "stale_document_ids")
        op.drop_column(table_name, "stale_reason")
        op.drop_column(table_name, "stale_at")

    op.drop_index("documents_project_active_primary_uidx", table_name="documents")
    op.execute(
        """
        CREATE UNIQUE INDEX documents_project_active_primary_uidx
        ON documents (project_id)
        WHERE is_primary = true AND active = true AND deleted_at IS NULL;
        """
    )
    op.drop_index("documents_archive_expires_idx", table_name="documents")
    op.drop_index("documents_project_lifecycle_idx", table_name="documents")
    op.drop_constraint("documents_lifecycle_status_check", "documents", type_="check")
    op.drop_column("documents", "hard_deleted_at")
    op.drop_column("documents", "archive_expires_at")
    op.drop_column("documents", "archived_at")
    op.drop_column("documents", "lifecycle_status")

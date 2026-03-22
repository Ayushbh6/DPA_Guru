"""Add approved checklist and final review persistence.

Revision ID: 20260322_0008
Revises: 20260322_0007
Create Date: 2026-03-22
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260322_0008"
down_revision = "20260322_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "approved_checklists",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("version", sa.String(length=128), nullable=False),
        sa.Column("selected_source_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("checklist_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("owner", sa.String(length=255), nullable=False),
        sa.Column("approval_status", sa.String(length=32), nullable=False),
        sa.Column("approved_by", sa.String(length=255), nullable=True),
        sa.Column("approved_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("change_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "approved_checklists_project_created_idx",
        "approved_checklists",
        ["project_id", "created_at"],
    )

    op.add_column("analysis_runs", sa.Column("stage", sa.String(length=64), nullable=True))
    op.add_column("analysis_runs", sa.Column("progress_pct", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column("analysis_runs", sa.Column("message", sa.Text(), nullable=True))
    op.add_column("analysis_runs", sa.Column("error_code", sa.String(length=128), nullable=True))
    op.add_column("analysis_runs", sa.Column("error_message", sa.Text(), nullable=True))
    op.add_column("analysis_runs", sa.Column("approved_checklist_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "analysis_runs_approved_checklist_id_fkey",
        "analysis_runs",
        "approved_checklists",
        ["approved_checklist_id"],
        ["id"],
    )
    op.create_index("analysis_runs_status_started_idx", "analysis_runs", ["status", "started_at"])

    op.add_column("findings", sa.Column("assessment_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    op.create_table(
        "analysis_reports",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("report_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("analysis_reports")

    op.drop_column("findings", "assessment_json")

    op.drop_index("analysis_runs_status_started_idx", table_name="analysis_runs")
    op.drop_constraint("analysis_runs_approved_checklist_id_fkey", "analysis_runs", type_="foreignkey")
    op.drop_column("analysis_runs", "approved_checklist_id")
    op.drop_column("analysis_runs", "error_message")
    op.drop_column("analysis_runs", "error_code")
    op.drop_column("analysis_runs", "message")
    op.drop_column("analysis_runs", "progress_pct")
    op.drop_column("analysis_runs", "stage")

    op.drop_index("approved_checklists_project_created_idx", table_name="approved_checklists")
    op.drop_table("approved_checklists")

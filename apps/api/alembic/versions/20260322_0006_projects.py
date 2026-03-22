"""Add project abstraction for end-to-end DPA analysis workflows.

Revision ID: 20260322_0006
Revises: 20260322_0005
Create Date: 2026-03-22
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260322_0006"
down_revision = "20260322_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'EMPTY'")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_activity_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_check_constraint(
        "projects_status_check",
        "projects",
        "status IN ('EMPTY', 'UPLOADING', 'READY_FOR_CHECKLIST', 'CHECKLIST_IN_PROGRESS', 'CHECKLIST_READY', 'REVIEW_IN_PROGRESS', 'COMPLETED', 'FAILED', 'DELETED')",
    )
    op.create_index("projects_tenant_last_activity_idx", "projects", ["tenant_id", "last_activity_at"])
    op.create_index("projects_status_updated_idx", "projects", ["status", "updated_at"])
    op.execute("ALTER TABLE projects ENABLE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY projects_tenant_isolation ON projects
        FOR ALL TO authenticated
        USING (tenant_id = app.current_tenant_id())
        WITH CHECK (tenant_id = app.current_tenant_id());
        """
    )

    op.add_column("documents", sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("document_parse_jobs", sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("checklist_draft_jobs", sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("analysis_runs", sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True))

    op.execute(
        """
        CREATE TEMP TABLE project_backfill_map (
          document_id uuid PRIMARY KEY,
          project_id uuid NOT NULL
        ) ON COMMIT DROP;

        INSERT INTO project_backfill_map (document_id, project_id)
        SELECT id, gen_random_uuid()
        FROM documents;

        INSERT INTO projects (id, tenant_id, name, status, created_at, updated_at, last_activity_at)
        SELECT
          map.project_id,
          d.tenant_id,
          CASE
            WHEN COALESCE(NULLIF(trim(d.filename), ''), '') = '' THEN 'Untitled analysis'
            ELSE 'Project for ' || d.filename
          END,
          CASE
            WHEN d.parse_status = 'COMPLETED' THEN 'READY_FOR_CHECKLIST'
            WHEN d.parse_status = 'FAILED' THEN 'FAILED'
            ELSE 'UPLOADING'
          END,
          COALESCE(d.uploaded_at, now()),
          COALESCE(d.parse_completed_at, d.uploaded_at, now()),
          COALESCE(d.parse_completed_at, d.uploaded_at, now())
        FROM documents d
        JOIN project_backfill_map map ON map.document_id = d.id;

        UPDATE documents d
        SET project_id = map.project_id
        FROM project_backfill_map map
        WHERE d.id = map.document_id;

        UPDATE document_parse_jobs j
        SET project_id = d.project_id
        FROM documents d
        WHERE j.document_id = d.id;

        UPDATE checklist_draft_jobs j
        SET project_id = d.project_id
        FROM documents d
        WHERE j.document_id = d.id;

        UPDATE analysis_runs r
        SET project_id = d.project_id
        FROM documents d
        WHERE r.document_id = d.id;
        """
    )

    op.alter_column("documents", "project_id", nullable=False)
    op.alter_column("document_parse_jobs", "project_id", nullable=False)
    op.alter_column("checklist_draft_jobs", "project_id", nullable=False)
    op.alter_column("analysis_runs", "project_id", nullable=False)

    op.create_foreign_key("documents_project_id_fkey", "documents", "projects", ["project_id"], ["id"])
    op.create_foreign_key(
        "document_parse_jobs_project_id_fkey",
        "document_parse_jobs",
        "projects",
        ["project_id"],
        ["id"],
    )
    op.create_foreign_key(
        "checklist_draft_jobs_project_id_fkey",
        "checklist_draft_jobs",
        "projects",
        ["project_id"],
        ["id"],
    )
    op.create_foreign_key("analysis_runs_project_id_fkey", "analysis_runs", "projects", ["project_id"], ["id"])

    op.create_unique_constraint("documents_project_uidx", "documents", ["project_id"])
    op.create_index("document_parse_jobs_project_created_idx", "document_parse_jobs", ["project_id", "created_at"])
    op.create_index("checklist_draft_jobs_project_created_idx", "checklist_draft_jobs", ["project_id", "created_at"])
    op.create_index("analysis_runs_project_started_idx", "analysis_runs", ["project_id", "started_at"])


def downgrade() -> None:
    op.drop_index("analysis_runs_project_started_idx", table_name="analysis_runs")
    op.drop_index("checklist_draft_jobs_project_created_idx", table_name="checklist_draft_jobs")
    op.drop_index("document_parse_jobs_project_created_idx", table_name="document_parse_jobs")
    op.drop_constraint("documents_project_uidx", "documents", type_="unique")

    op.drop_constraint("analysis_runs_project_id_fkey", "analysis_runs", type_="foreignkey")
    op.drop_constraint("checklist_draft_jobs_project_id_fkey", "checklist_draft_jobs", type_="foreignkey")
    op.drop_constraint("document_parse_jobs_project_id_fkey", "document_parse_jobs", type_="foreignkey")
    op.drop_constraint("documents_project_id_fkey", "documents", type_="foreignkey")

    op.drop_column("analysis_runs", "project_id")
    op.drop_column("checklist_draft_jobs", "project_id")
    op.drop_column("document_parse_jobs", "project_id")
    op.drop_column("documents", "project_id")

    op.execute("DROP POLICY IF EXISTS projects_tenant_isolation ON projects;")
    op.drop_index("projects_status_updated_idx", table_name="projects")
    op.drop_index("projects_tenant_last_activity_idx", table_name="projects")
    op.drop_constraint("projects_status_check", "projects", type_="check")
    op.drop_table("projects")

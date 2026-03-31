"""Add checklist synthesis trace tables and checklist job meta.

Revision ID: 20260330_0013
Revises: 20260330_0012
Create Date: 2026-03-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260330_0013"
down_revision = "20260330_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("checklist_draft_jobs", sa.Column("meta_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    op.create_table(
        "checklist_synthesis_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "checklist_draft_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("checklist_draft_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("strategy_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("fallback_used", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("partial_drafts_total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("candidate_checks_total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("candidate_pairs_total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("candidate_pairs_verified", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("merge_groups_total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("merge_groups_completed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index(
        "checklist_synthesis_runs_draft_started_idx",
        "checklist_synthesis_runs",
        ["checklist_draft_id", "started_at"],
    )

    op.create_table(
        "checklist_synthesis_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "synthesis_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("checklist_synthesis_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("synthesis_run_id", "sequence_no", name="checklist_synthesis_events_run_sequence_uidx"),
    )
    op.create_index(
        "checklist_synthesis_events_run_created_idx",
        "checklist_synthesis_events",
        ["synthesis_run_id", "created_at"],
    )

    op.execute("ALTER TABLE checklist_synthesis_runs ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE checklist_synthesis_events ENABLE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY checklist_synthesis_runs_tenant_isolation ON checklist_synthesis_runs
        FOR ALL TO PUBLIC
        USING (
          checklist_draft_id IN (
            SELECT id FROM checklist_draft_jobs WHERE tenant_id = app.current_tenant_id()
          )
        )
        WITH CHECK (
          checklist_draft_id IN (
            SELECT id FROM checklist_draft_jobs WHERE tenant_id = app.current_tenant_id()
          )
        );
        """
    )
    op.execute(
        """
        CREATE POLICY checklist_synthesis_events_tenant_isolation ON checklist_synthesis_events
        FOR ALL TO PUBLIC
        USING (
          synthesis_run_id IN (
            SELECT csr.id
            FROM checklist_synthesis_runs csr
            JOIN checklist_draft_jobs cdj ON cdj.id = csr.checklist_draft_id
            WHERE cdj.tenant_id = app.current_tenant_id()
          )
        )
        WITH CHECK (
          synthesis_run_id IN (
            SELECT csr.id
            FROM checklist_synthesis_runs csr
            JOIN checklist_draft_jobs cdj ON cdj.id = csr.checklist_draft_id
            WHERE cdj.tenant_id = app.current_tenant_id()
          )
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS checklist_synthesis_events_tenant_isolation ON checklist_synthesis_events;")
    op.execute("DROP POLICY IF EXISTS checklist_synthesis_runs_tenant_isolation ON checklist_synthesis_runs;")
    op.drop_index("checklist_synthesis_events_run_created_idx", table_name="checklist_synthesis_events")
    op.drop_table("checklist_synthesis_events")
    op.drop_index("checklist_synthesis_runs_draft_started_idx", table_name="checklist_synthesis_runs")
    op.drop_table("checklist_synthesis_runs")
    op.drop_column("checklist_draft_jobs", "meta_json")

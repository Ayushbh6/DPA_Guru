"""Add Phase 4 copilot conversation tables.

Revision ID: 20260614_0017
Revises: 20260613_0016
Create Date: 2026-06-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260614_0017"
down_revision = "20260613_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "copilot_threads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("approval_pack_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("approval_packs.id"), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'active'")),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_check_constraint("copilot_threads_status_check", "copilot_threads", "status IN ('active', 'archived')")
    op.create_index("copilot_threads_project_updated_idx", "copilot_threads", ["project_id", "updated_at"])

    op.create_table(
        "copilot_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("copilot_threads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("model_version", sa.String(length=128), nullable=True),
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_runs.id"), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'completed'")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_check_constraint("copilot_messages_role_check", "copilot_messages", "role IN ('user', 'assistant', 'system', 'tool')")
    op.create_check_constraint("copilot_messages_status_check", "copilot_messages", "status IN ('queued', 'running', 'completed', 'failed')")
    op.create_index("copilot_messages_thread_created_idx", "copilot_messages", ["thread_id", "created_at"])
    op.create_index("copilot_messages_project_created_idx", "copilot_messages", ["project_id", "created_at"])
    op.create_index("agent_runs_copilot_thread_created_idx", "agent_runs", ["copilot_thread_id", "created_at"])


def downgrade() -> None:
    op.drop_index("agent_runs_copilot_thread_created_idx", table_name="agent_runs")
    op.drop_index("copilot_messages_project_created_idx", table_name="copilot_messages")
    op.drop_index("copilot_messages_thread_created_idx", table_name="copilot_messages")
    op.drop_table("copilot_messages")
    op.drop_index("copilot_threads_project_updated_idx", table_name="copilot_threads")
    op.drop_table("copilot_threads")

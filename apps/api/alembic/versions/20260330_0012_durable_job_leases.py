"""Add durable worker lease fields to persisted job tables.

Revision ID: 20260330_0012
Revises: 20260329_0011
Create Date: 2026-03-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260330_0012"
down_revision = "20260329_0011"
branch_labels = None
depends_on = None


def _add_durable_job_columns(table_name: str) -> None:
    op.add_column(table_name, sa.Column("claimed_by_worker", sa.String(length=255), nullable=True))
    op.add_column(table_name, sa.Column("claimed_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column(table_name, sa.Column("heartbeat_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column(table_name, sa.Column("lease_expires_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column(table_name, sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column(table_name, sa.Column("available_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")))
    op.add_column(table_name, sa.Column("last_error_code", sa.String(length=128), nullable=True))
    op.add_column(table_name, sa.Column("last_error_message", sa.Text(), nullable=True))


def _drop_durable_job_columns(table_name: str) -> None:
    op.drop_column(table_name, "last_error_message")
    op.drop_column(table_name, "last_error_code")
    op.drop_column(table_name, "available_at")
    op.drop_column(table_name, "attempt_count")
    op.drop_column(table_name, "lease_expires_at")
    op.drop_column(table_name, "heartbeat_at")
    op.drop_column(table_name, "claimed_at")
    op.drop_column(table_name, "claimed_by_worker")


def upgrade() -> None:
    _add_durable_job_columns("document_parse_jobs")
    _add_durable_job_columns("checklist_draft_jobs")
    _add_durable_job_columns("analysis_runs")


def downgrade() -> None:
    _drop_durable_job_columns("analysis_runs")
    _drop_durable_job_columns("checklist_draft_jobs")
    _drop_durable_job_columns("document_parse_jobs")

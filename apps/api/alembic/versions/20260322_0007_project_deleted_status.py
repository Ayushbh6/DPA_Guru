"""Allow soft-deleted projects in the status constraint.

Revision ID: 20260322_0007
Revises: 20260322_0006
Create Date: 2026-03-22
"""

from __future__ import annotations

from alembic import op


revision = "20260322_0007"
down_revision = "20260322_0006"
branch_labels = None
depends_on = None


PROJECT_STATUS_CHECK = (
    "status IN ("
    "'EMPTY', "
    "'UPLOADING', "
    "'READY_FOR_CHECKLIST', "
    "'CHECKLIST_IN_PROGRESS', "
    "'CHECKLIST_READY', "
    "'REVIEW_IN_PROGRESS', "
    "'COMPLETED', "
    "'FAILED', "
    "'DELETED'"
    ")"
)

PROJECT_STATUS_CHECK_DOWNGRADE = (
    "status IN ("
    "'EMPTY', "
    "'UPLOADING', "
    "'READY_FOR_CHECKLIST', "
    "'CHECKLIST_IN_PROGRESS', "
    "'CHECKLIST_READY', "
    "'REVIEW_IN_PROGRESS', "
    "'COMPLETED', "
    "'FAILED'"
    ")"
)


def upgrade() -> None:
    op.drop_constraint("projects_status_check", "projects", type_="check")
    op.create_check_constraint("projects_status_check", "projects", PROJECT_STATUS_CHECK)


def downgrade() -> None:
    op.drop_constraint("projects_status_check", "projects", type_="check")
    op.create_check_constraint("projects_status_check", "projects", PROJECT_STATUS_CHECK_DOWNGRADE)

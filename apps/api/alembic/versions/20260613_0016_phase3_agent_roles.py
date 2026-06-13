"""Allow Phase 3 agent roles in agent_runs.

Revision ID: 20260613_0016
Revises: 20260612_0015
Create Date: 2026-06-13
"""

from __future__ import annotations

from alembic import op


revision = "20260613_0016"
down_revision = "20260612_0015"
branch_labels = None
depends_on = None


_AGENT_ROLE_CHECK = (
    "agent_role IN ("
    "'checklist_draft', 'checklist_synthesis', 'per_check_review', 'review_synthesis', "
    "'evidence', 'risk', 'recommendation', 'action_pack', 'assembler', 'copilot', 'report_revision', "
    "'criteria', 'criteria_research', 'review', 'approval_pack'"
    ")"
)


def upgrade() -> None:
    op.drop_constraint("agent_runs_agent_role_check", "agent_runs", type_="check")
    op.create_check_constraint("agent_runs_agent_role_check", "agent_runs", _AGENT_ROLE_CHECK)


def downgrade() -> None:
    op.drop_constraint("agent_runs_agent_role_check", "agent_runs", type_="check")
    op.create_check_constraint(
        "agent_runs_agent_role_check",
        "agent_runs",
        (
            "agent_role IN ("
            "'checklist_draft', 'checklist_synthesis', 'per_check_review', 'review_synthesis', "
            "'evidence', 'risk', 'recommendation', 'action_pack', 'assembler', 'copilot', 'report_revision'"
            ")"
        ),
    )

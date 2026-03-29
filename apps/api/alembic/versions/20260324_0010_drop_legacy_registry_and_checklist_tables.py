"""Drop archived registry tables and unused normalized checklist tables.

Revision ID: 20260324_0010
Revises: 20260323_0009
Create Date: 2026-03-24
"""

from __future__ import annotations

from alembic import op


revision = "20260324_0010"
down_revision = "20260323_0009"
branch_labels = None
depends_on = None


LEGACY_TABLES = (
    "registry_audit_events",
    "registry_checklist_synthesis_runs",
    "registry_diffs",
    "registry_extracted_obligations",
    "registry_extraction_segments",
    "registry_extraction_chunks",
    "registry_extraction_runs",
    "registry_snapshots",
    "registry_sources",
    "checklist_approvals",
    "checklist_item_sources",
    "checklist_reviews",
    "checklist_items",
    "checklist_versions",
)


def upgrade() -> None:
    for table_name in LEGACY_TABLES:
        op.execute(f'DROP TABLE IF EXISTS "{table_name}" CASCADE;')


def downgrade() -> None:
    # Intentionally no-op.
    #
    # These tables are archived / unused legacy structures and are no longer part
    # of the active schema path. Recreating them during downgrade would require
    # reintroducing the retired schema and its historical semantics.
    return None

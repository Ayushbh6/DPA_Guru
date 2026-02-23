"""Compatibility no-op for archived experimental registry extraction migration.

Revision ID: 20260222_0003
Revises: 20260217_0001
Create Date: 2026-02-23

This project temporarily used revision ID ``20260222_0003`` for an experimental
registry extraction pipeline migration that has since been archived to
``.future_work/`` and removed from the active codebase.

Some local developer databases are still stamped to that revision. This no-op
compatibility stub preserves Alembic graph continuity so those databases can
continue upgrading to the new KB ingestion pipeline migration.
"""

from __future__ import annotations

revision = "20260222_0003"
down_revision = "20260217_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Intentionally no-op. The archived experimental migration is no longer part
    # of the active schema path, but we keep the revision ID for compatibility.
    return None


def downgrade() -> None:
    # Intentionally no-op.
    return None

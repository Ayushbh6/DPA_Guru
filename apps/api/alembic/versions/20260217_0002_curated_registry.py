"""Curated source registry and checklist versioning tables.

Revision ID: 20260217_0002
Revises: 20260217_0001
Create Date: 2026-02-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260217_0002"
down_revision = "20260217_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "registry_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_id", sa.String(length=128), nullable=False, unique=True),
        sa.Column("authority", sa.String(length=255), nullable=False),
        sa.Column("celex_or_doc_id", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("languages", postgresql.ARRAY(sa.String(length=8)), nullable=False),
        sa.Column("status_rule", sa.String(length=64), nullable=False),
        sa.Column("fetch_url_map", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_check_constraint(
        "registry_sources_type_check",
        "registry_sources",
        "source_type IN ('LAW', 'GUIDELINE', 'MONITOR')",
    )

    op.create_table(
        "registry_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "registry_source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("registry_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("fetched_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("http_etag", sa.String(length=512), nullable=True),
        sa.Column("http_last_modified", sa.String(length=512), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("raw_storage_path", sa.Text(), nullable=False),
        sa.Column("parsed_storage_path", sa.Text(), nullable=True),
        sa.Column("parse_status", sa.String(length=32), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("tracked_sections", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_check_constraint(
        "registry_snapshots_parse_status_check",
        "registry_snapshots",
        "parse_status IN ('PARSED', 'RAW_ONLY', 'FAILED')",
    )
    op.execute(
        "CREATE INDEX registry_snapshots_source_lang_fetched_idx ON registry_snapshots (source_id, language, fetched_at DESC);"
    )
    op.create_index(
        "registry_snapshots_sha_idx",
        "registry_snapshots",
        ["source_id", "language", "sha256"],
        unique=False,
    )

    op.create_table(
        "registry_diffs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "registry_source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("registry_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column(
            "from_snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("registry_snapshots.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "to_snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("registry_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("change_class", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("changed_sections", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("token_change_ratio", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_check_constraint(
        "registry_diffs_change_class_check",
        "registry_diffs",
        "change_class IN ('NO_CHANGE', 'MINOR_TEXT_CHANGE', 'MATERIAL_CHANGE')",
    )
    op.execute(
        "CREATE INDEX registry_diffs_source_lang_created_idx ON registry_diffs (source_id, language, created_at DESC);"
    )

    op.create_table(
        "checklist_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("version_id", sa.String(length=128), nullable=False, unique=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("generated_from_snapshot_set", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("governance", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("checklist_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("approved_by", sa.String(length=128), nullable=True),
        sa.Column("approved_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "checklist_versions_status_check",
        "checklist_versions",
        "status IN ('DRAFT', 'REVIEWED', 'REJECTED', 'ACTIVE', 'ARCHIVED', 'FAILED_CLOSED')",
    )
    op.execute(
        "CREATE UNIQUE INDEX checklist_versions_single_active_idx ON checklist_versions (is_active) WHERE is_active = true;"
    )

    op.create_table(
        "checklist_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "checklist_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("checklist_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("check_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=128), nullable=False),
        sa.Column("legal_basis", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("evidence_hint", sa.Text(), nullable=False),
        sa.Column("pass_criteria", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("fail_criteria", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("sort_order", sa.Integer(), nullable=False),
    )
    op.create_check_constraint(
        "checklist_items_severity_check",
        "checklist_items",
        "severity IN ('LOW', 'MEDIUM', 'HIGH', 'MANDATORY')",
    )
    op.create_index(
        "checklist_items_version_check_idx",
        "checklist_items",
        ["checklist_version_id", "check_id"],
        unique=True,
    )

    op.create_table(
        "checklist_item_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "checklist_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("checklist_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("authority", sa.String(length=255), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_excerpt", sa.Text(), nullable=False),
        sa.Column("interpretation_notes", sa.Text(), nullable=True),
    )
    op.create_check_constraint(
        "checklist_item_sources_type_check",
        "checklist_item_sources",
        "source_type IN ('LAW', 'GUIDELINE', 'INTERNAL_POLICY')",
    )
    op.create_index(
        "checklist_item_sources_item_idx",
        "checklist_item_sources",
        ["checklist_item_id"],
        unique=False,
    )

    op.create_table(
        "checklist_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "checklist_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("checklist_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reviewer_id", sa.String(length=128), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_check_constraint(
        "checklist_reviews_decision_check",
        "checklist_reviews",
        "decision IN ('REVIEWED', 'REJECTED')",
    )

    op.create_table(
        "checklist_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "checklist_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("checklist_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("approver_id", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_check_constraint(
        "checklist_approvals_action_check",
        "checklist_approvals",
        "action IN ('APPROVED_AND_PROMOTED', 'ROLLBACK_PROMOTE')",
    )

    op.create_table(
        "registry_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("actor_type", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("event_name", sa.String(length=128), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=128), nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("registry_audit_events_trace_idx", "registry_audit_events", ["trace_id"], unique=False)


def downgrade() -> None:
    op.drop_index("registry_audit_events_trace_idx", table_name="registry_audit_events")
    op.drop_table("registry_audit_events")

    op.drop_table("checklist_approvals")
    op.drop_table("checklist_reviews")
    op.drop_index("checklist_item_sources_item_idx", table_name="checklist_item_sources")
    op.drop_table("checklist_item_sources")
    op.drop_index("checklist_items_version_check_idx", table_name="checklist_items")
    op.drop_table("checklist_items")
    op.execute("DROP INDEX IF EXISTS checklist_versions_single_active_idx;")
    op.drop_table("checklist_versions")

    op.drop_index("registry_diffs_source_lang_created_idx", table_name="registry_diffs")
    op.drop_table("registry_diffs")
    op.drop_index("registry_snapshots_sha_idx", table_name="registry_snapshots")
    op.drop_index("registry_snapshots_source_lang_fetched_idx", table_name="registry_snapshots")
    op.drop_table("registry_snapshots")
    op.drop_table("registry_sources")

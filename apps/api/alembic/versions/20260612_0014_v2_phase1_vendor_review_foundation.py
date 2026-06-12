"""Add V2 vendor review, agent run, and approval pack foundation.

Revision ID: 20260612_0014
Revises: 20260330_0013
Create Date: 2026-06-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260612_0014"
down_revision = "20260330_0013"
branch_labels = None
depends_on = None


def _enable_tenant_rls(table_name: str) -> None:
    op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;")
    op.execute(
        f"""
        CREATE POLICY {table_name}_tenant_isolation ON {table_name}
        FOR ALL TO PUBLIC
        USING (tenant_id = app.current_tenant_id())
        WITH CHECK (tenant_id = app.current_tenant_id());
        """
    )


def _drop_tenant_rls(table_name: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS {table_name}_tenant_isolation ON {table_name};")


def upgrade() -> None:
    # Vendor Review context on the existing project workspace table.
    op.add_column("projects", sa.Column("review_type", sa.String(length=64), nullable=False, server_default="vendor_dpa_review"))
    op.add_column("projects", sa.Column("vendor_name", sa.String(length=255), nullable=True))
    op.add_column("projects", sa.Column("vendor_website", sa.Text(), nullable=True))
    op.add_column("projects", sa.Column("tool_or_service_name", sa.String(length=255), nullable=True))
    op.add_column("projects", sa.Column("intended_use_case", sa.Text(), nullable=True))
    op.add_column("projects", sa.Column("data_types", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("projects", sa.Column("shares_personal_data", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("projects", sa.Column("shares_customer_data", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("projects", sa.Column("shares_employee_data", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("projects", sa.Column("shares_sensitive_data", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("projects", sa.Column("has_ai_features", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("projects", sa.Column("business_criticality", sa.String(length=16), nullable=True))
    op.add_column("projects", sa.Column("vendor_region", sa.String(length=32), nullable=True))
    op.add_column("projects", sa.Column("processes_eu_personal_data", sa.Boolean(), nullable=True))
    op.add_column("projects", sa.Column("transfers_data_outside_eea", sa.Boolean(), nullable=True))
    op.add_column("projects", sa.Column("internal_owner", sa.String(length=255), nullable=True))
    op.add_column("projects", sa.Column("review_deadline", sa.Date(), nullable=True))
    op.add_column("projects", sa.Column("current_approval_pack_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("projects", sa.Column("current_recommendation", sa.String(length=32), nullable=True))
    op.add_column("projects", sa.Column("context_completed_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.create_check_constraint("projects_review_type_check", "projects", "review_type IN ('vendor_dpa_review')")
    op.create_check_constraint("projects_business_criticality_check", "projects", "business_criticality IS NULL OR business_criticality IN ('low', 'medium', 'high')")
    op.create_check_constraint("projects_vendor_region_check", "projects", "vendor_region IS NULL OR vendor_region IN ('EU_EEA', 'US', 'UK', 'OTHER', 'UNKNOWN')")
    op.create_check_constraint(
        "projects_current_recommendation_check",
        "projects",
        "current_recommendation IS NULL OR current_recommendation IN ('approve', 'approve_with_conditions', 'escalate', 'reject')",
    )
    op.create_index("projects_tenant_vendor_name_idx", "projects", ["tenant_id", "vendor_name"])
    op.create_index("projects_tenant_recommendation_activity_idx", "projects", ["tenant_id", "current_recommendation", "last_activity_at"])

    # Multi-document support. Existing projects had at most one document, so
    # backfill every existing document as the active primary DPA.
    op.drop_constraint("documents_project_uidx", "documents", type_="unique")
    op.add_column("documents", sa.Column("document_type", sa.String(length=64), nullable=False, server_default="main_dpa"))
    op.add_column("documents", sa.Column("display_name", sa.String(length=512), nullable=True))
    op.add_column("documents", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("documents", sa.Column("source_kind", sa.String(length=32), nullable=False, server_default="uploaded"))
    op.add_column("documents", sa.Column("source_url", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("uploaded_by", sa.String(length=255), nullable=True))
    op.add_column("documents", sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("documents", sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("documents", sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.execute("UPDATE documents SET is_primary = true WHERE deleted_at IS NULL;")
    op.create_check_constraint(
        "documents_document_type_check",
        "documents",
        "document_type IN ('main_dpa', 'privacy_policy', 'security_toms', 'subprocessors', 'data_transfer_terms', 'ai_terms', 'service_terms', 'security_certification', 'custom_agreement', 'other')",
    )
    op.create_check_constraint("documents_source_kind_check", "documents", "source_kind IN ('uploaded', 'web', 'system')")
    op.create_index("documents_project_type_uploaded_idx", "documents", ["project_id", "document_type", "uploaded_at"])
    op.create_index("documents_project_primary_idx", "documents", ["project_id", "is_primary"])
    op.create_index("documents_project_active_sort_idx", "documents", ["project_id", "active", "sort_order"])
    op.execute(
        """
        CREATE UNIQUE INDEX documents_project_active_primary_uidx
        ON documents (project_id)
        WHERE is_primary = true AND active = true AND deleted_at IS NULL;
        """
    )

    op.add_column("document_chunks", sa.Column("section_title", sa.Text(), nullable=True))
    op.add_column("document_chunks", sa.Column("chunk_index", sa.Integer(), nullable=True))
    op.add_column("document_chunks", sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_index("document_chunks_document_page_idx", "document_chunks", ["document_id", "page_start", "page_end"])

    op.add_column("checklist_draft_jobs", sa.Column("review_mode", sa.String(length=64), nullable=False, server_default="vendor_dpa_review"))
    op.add_column("checklist_draft_jobs", sa.Column("profile_id", sa.String(length=128), nullable=False, server_default="standard_vendor_dpa_v1"))
    op.add_column("checklist_draft_jobs", sa.Column("input_document_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("checklist_draft_jobs", sa.Column("vendor_context_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    op.add_column("approved_checklists", sa.Column("review_mode", sa.String(length=64), nullable=False, server_default="vendor_dpa_review"))
    op.add_column("approved_checklists", sa.Column("profile_id", sa.String(length=128), nullable=False, server_default="standard_vendor_dpa_v1"))
    op.add_column("approved_checklists", sa.Column("input_document_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("approved_checklists", sa.Column("vendor_context_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("approved_checklists", sa.Column("auto_approved", sa.Boolean(), nullable=False, server_default=sa.text("false")))

    op.add_column("analysis_runs", sa.Column("review_mode", sa.String(length=64), nullable=False, server_default="vendor_dpa_review"))
    op.add_column("analysis_runs", sa.Column("primary_document_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("analysis_runs", sa.Column("input_document_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("analysis_runs", sa.Column("vendor_context_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_foreign_key("analysis_runs_primary_document_id_fkey", "analysis_runs", "documents", ["primary_document_id"], ["id"])

    op.add_column("findings", sa.Column("severity", sa.String(length=16), nullable=True))
    op.add_column("findings", sa.Column("business_impact", sa.Text(), nullable=True))
    op.add_column("findings", sa.Column("recommendation", sa.Text(), nullable=True))
    op.add_column("findings", sa.Column("evidence_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")))

    op.add_column("analysis_reports", sa.Column("report_type", sa.String(length=64), nullable=False, server_default="legacy_output_v2"))

    op.add_column("rule_hits", sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("rule_hits_document_id_fkey", "rule_hits", "documents", ["document_id"], ["id"])

    op.create_table(
        "analysis_run_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("analysis_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("document_type", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("included", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("analysis_run_id", "document_id", name="analysis_run_documents_run_document_uidx"),
    )
    op.create_check_constraint("analysis_run_documents_role_check", "analysis_run_documents", "role IN ('primary', 'supporting', 'excluded')")
    op.create_index("analysis_run_documents_run_role_idx", "analysis_run_documents", ["analysis_run_id", "role"])
    op.create_index("analysis_run_documents_project_type_idx", "analysis_run_documents", ["project_id", "document_type"])

    op.create_table(
        "approval_packs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("analysis_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id"), nullable=True),
        sa.Column("approved_checklist_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("approved_checklists.id"), nullable=True),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("recommendation", sa.String(length=32), nullable=False),
        sa.Column("recommendation_summary", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("review_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("pack_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_report_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("generated_by", sa.String(length=64), nullable=False, server_default="system"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_check_constraint("approval_packs_status_check", "approval_packs", "status IN ('draft', 'published', 'superseded', 'archived')")
    op.create_check_constraint(
        "approval_packs_recommendation_check",
        "approval_packs",
        "recommendation IN ('approve', 'approve_with_conditions', 'escalate', 'reject')",
    )
    op.create_check_constraint("approval_packs_confidence_check", "approval_packs", "confidence >= 0 AND confidence <= 1")
    op.create_index("approval_packs_project_created_idx", "approval_packs", ["project_id", "created_at"])
    op.create_index("approval_packs_tenant_recommendation_created_idx", "approval_packs", ["tenant_id", "recommendation", "created_at"])
    op.execute(
        """
        CREATE INDEX approval_packs_project_active_idx
        ON approval_packs (project_id)
        WHERE status IN ('draft', 'published');
        """
    )
    op.create_foreign_key(
        "projects_current_approval_pack_id_fkey",
        "projects",
        "approval_packs",
        ["current_approval_pack_id"],
        ["id"],
    )

    op.create_table(
        "agent_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("analysis_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id"), nullable=True),
        sa.Column("approval_pack_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("approval_packs.id"), nullable=True),
        sa.Column("copilot_thread_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("parent_agent_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_runs.id"), nullable=True),
        sa.Column("agent_name", sa.String(length=128), nullable=False),
        sa.Column("agent_role", sa.String(length=64), nullable=False),
        sa.Column("agent_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("model_provider", sa.String(length=64), nullable=True),
        sa.Column("model_name", sa.String(length=128), nullable=True),
        sa.Column("model_version", sa.String(length=128), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("system_prompt_hash", sa.String(length=64), nullable=True),
        sa.Column("input_hash", sa.String(length=64), nullable=True),
        sa.Column("output_hash", sa.String(length=64), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_check_constraint(
        "agent_runs_agent_role_check",
        "agent_runs",
        "agent_role IN ('checklist_draft', 'checklist_synthesis', 'per_check_review', 'review_synthesis', 'evidence', 'risk', 'recommendation', 'action_pack', 'assembler', 'copilot', 'report_revision')",
    )
    op.create_check_constraint("agent_runs_status_check", "agent_runs", "status IN ('queued', 'running', 'completed', 'failed', 'canceled')")
    op.create_index("agent_runs_project_created_idx", "agent_runs", ["project_id", "created_at"])
    op.create_index("agent_runs_analysis_created_idx", "agent_runs", ["analysis_run_id", "created_at"])
    op.create_index("agent_runs_approval_pack_created_idx", "agent_runs", ["approval_pack_id", "created_at"])
    op.create_index("agent_runs_role_status_created_idx", "agent_runs", ["agent_role", "status", "created_at"])
    op.execute(
        """
        CREATE UNIQUE INDEX agent_runs_tenant_idempotency_uidx
        ON agent_runs (tenant_id, idempotency_key)
        WHERE idempotency_key IS NOT NULL;
        """
    )

    op.create_table(
        "agent_run_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("content_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("agent_run_id", "sequence_no", name="agent_run_messages_run_sequence_uidx"),
    )
    op.create_check_constraint("agent_run_messages_role_check", "agent_run_messages", "role IN ('system', 'developer', 'user', 'assistant', 'tool')")
    op.create_index("agent_run_messages_run_sequence_idx", "agent_run_messages", ["agent_run_id", "sequence_no"])

    op.create_table(
        "agent_run_tool_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_run_messages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("input_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("agent_run_id", "sequence_no", name="agent_run_tool_calls_run_sequence_uidx"),
    )
    op.create_check_constraint("agent_run_tool_calls_status_check", "agent_run_tool_calls", "status IN ('queued', 'running', 'completed', 'failed', 'canceled')")
    op.create_index("agent_run_tool_calls_run_sequence_idx", "agent_run_tool_calls", ["agent_run_id", "sequence_no"])
    op.create_index("agent_run_tool_calls_tool_created_idx", "agent_run_tool_calls", ["tool_name", "created_at"])

    op.create_table(
        "agent_run_outputs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("output_type", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("output_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("validation_status", sa.String(length=32), nullable=False),
        sa.Column("validation_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_check_constraint("agent_run_outputs_validation_status_check", "agent_run_outputs", "validation_status IN ('valid', 'invalid', 'skipped')")
    op.create_index("agent_run_outputs_run_type_idx", "agent_run_outputs", ["agent_run_id", "output_type"])
    op.create_index("agent_run_outputs_type_created_idx", "agent_run_outputs", ["output_type", "created_at"])

    op.create_table(
        "agent_run_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("agent_run_id", "sequence_no", name="agent_run_events_run_sequence_uidx"),
    )
    op.create_index("agent_run_events_run_sequence_idx", "agent_run_events", ["agent_run_id", "sequence_no"])
    op.create_index("agent_run_events_run_created_idx", "agent_run_events", ["agent_run_id", "created_at"])

    op.create_table(
        "agent_run_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_type", sa.String(length=64), nullable=False),
        sa.Column("storage_provider", sa.String(length=32), nullable=False),
        sa.Column("object_uri", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("agent_run_artifacts_run_type_created_idx", "agent_run_artifacts", ["agent_run_id", "artifact_type", "created_at"])

    op.create_table(
        "approval_pack_stage_outputs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("analysis_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id"), nullable=True),
        sa.Column("approval_pack_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("approval_packs.id", ondelete="CASCADE"), nullable=True),
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_runs.id"), nullable=True),
        sa.Column("stage_name", sa.String(length=64), nullable=False),
        sa.Column("stage_version", sa.String(length=64), nullable=False),
        sa.Column("model_version", sa.String(length=128), nullable=True),
        sa.Column("input_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("output_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_check_constraint("approval_pack_stage_outputs_stage_name_check", "approval_pack_stage_outputs", "stage_name IN ('evidence', 'risk', 'recommendation', 'action_pack', 'assembler')")
    op.create_check_constraint("approval_pack_stage_outputs_status_check", "approval_pack_stage_outputs", "status IN ('completed', 'failed', 'skipped')")
    op.create_index("approval_pack_stage_outputs_pack_stage_idx", "approval_pack_stage_outputs", ["approval_pack_id", "stage_name"])
    op.create_index("approval_pack_stage_outputs_analysis_created_idx", "approval_pack_stage_outputs", ["analysis_run_id", "created_at"])
    op.create_index("approval_pack_stage_outputs_agent_run_idx", "approval_pack_stage_outputs", ["agent_run_id"])

    op.create_table(
        "approval_pack_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("approval_pack_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("approval_packs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_type", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("changes_summary", sa.Text(), nullable=False),
        sa.Column("patch_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("previous_pack_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_pack_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("applied_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_check_constraint("approval_pack_revisions_created_by_type_check", "approval_pack_revisions", "created_by_type IN ('user', 'copilot', 'system')")
    op.create_check_constraint("approval_pack_revisions_status_check", "approval_pack_revisions", "status IN ('proposed', 'applied', 'rejected')")
    op.create_index("approval_pack_revisions_pack_created_idx", "approval_pack_revisions", ["approval_pack_id", "created_at"])
    op.create_index("approval_pack_revisions_project_status_created_idx", "approval_pack_revisions", ["project_id", "status", "created_at"])

    op.add_column("review_actions", sa.Column("approval_pack_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("review_actions_approval_pack_id_fkey", "review_actions", "approval_packs", ["approval_pack_id"], ["id"])

    for table_name in (
        "analysis_run_documents",
        "approval_packs",
        "agent_runs",
        "agent_run_messages",
        "agent_run_tool_calls",
        "agent_run_outputs",
        "agent_run_events",
        "agent_run_artifacts",
        "approval_pack_stage_outputs",
        "approval_pack_revisions",
    ):
        _enable_tenant_rls(table_name)


def downgrade() -> None:
    op.drop_constraint("review_actions_approval_pack_id_fkey", "review_actions", type_="foreignkey")
    op.drop_column("review_actions", "approval_pack_id")

    for table_name in (
        "approval_pack_revisions",
        "approval_pack_stage_outputs",
        "agent_run_artifacts",
        "agent_run_events",
        "agent_run_outputs",
        "agent_run_tool_calls",
        "agent_run_messages",
        "agent_runs",
        "approval_packs",
        "analysis_run_documents",
    ):
        _drop_tenant_rls(table_name)

    op.drop_index("approval_pack_revisions_project_status_created_idx", table_name="approval_pack_revisions")
    op.drop_index("approval_pack_revisions_pack_created_idx", table_name="approval_pack_revisions")
    op.drop_table("approval_pack_revisions")

    op.drop_index("approval_pack_stage_outputs_agent_run_idx", table_name="approval_pack_stage_outputs")
    op.drop_index("approval_pack_stage_outputs_analysis_created_idx", table_name="approval_pack_stage_outputs")
    op.drop_index("approval_pack_stage_outputs_pack_stage_idx", table_name="approval_pack_stage_outputs")
    op.drop_table("approval_pack_stage_outputs")

    op.drop_index("agent_run_artifacts_run_type_created_idx", table_name="agent_run_artifacts")
    op.drop_table("agent_run_artifacts")

    op.drop_index("agent_run_events_run_created_idx", table_name="agent_run_events")
    op.drop_index("agent_run_events_run_sequence_idx", table_name="agent_run_events")
    op.drop_table("agent_run_events")

    op.drop_index("agent_run_outputs_type_created_idx", table_name="agent_run_outputs")
    op.drop_index("agent_run_outputs_run_type_idx", table_name="agent_run_outputs")
    op.drop_table("agent_run_outputs")

    op.drop_index("agent_run_tool_calls_tool_created_idx", table_name="agent_run_tool_calls")
    op.drop_index("agent_run_tool_calls_run_sequence_idx", table_name="agent_run_tool_calls")
    op.drop_table("agent_run_tool_calls")

    op.drop_index("agent_run_messages_run_sequence_idx", table_name="agent_run_messages")
    op.drop_table("agent_run_messages")

    op.drop_index("agent_runs_tenant_idempotency_uidx", table_name="agent_runs")
    op.drop_index("agent_runs_role_status_created_idx", table_name="agent_runs")
    op.drop_index("agent_runs_approval_pack_created_idx", table_name="agent_runs")
    op.drop_index("agent_runs_analysis_created_idx", table_name="agent_runs")
    op.drop_index("agent_runs_project_created_idx", table_name="agent_runs")
    op.drop_table("agent_runs")

    op.drop_constraint("projects_current_approval_pack_id_fkey", "projects", type_="foreignkey")
    op.drop_index("approval_packs_project_active_idx", table_name="approval_packs")
    op.drop_index("approval_packs_tenant_recommendation_created_idx", table_name="approval_packs")
    op.drop_index("approval_packs_project_created_idx", table_name="approval_packs")
    op.drop_table("approval_packs")

    op.drop_index("analysis_run_documents_project_type_idx", table_name="analysis_run_documents")
    op.drop_index("analysis_run_documents_run_role_idx", table_name="analysis_run_documents")
    op.drop_table("analysis_run_documents")

    op.drop_constraint("rule_hits_document_id_fkey", "rule_hits", type_="foreignkey")
    op.drop_column("rule_hits", "document_id")

    op.drop_column("analysis_reports", "report_type")

    op.drop_column("findings", "evidence_json")
    op.drop_column("findings", "recommendation")
    op.drop_column("findings", "business_impact")
    op.drop_column("findings", "severity")

    op.drop_constraint("analysis_runs_primary_document_id_fkey", "analysis_runs", type_="foreignkey")
    op.drop_column("analysis_runs", "vendor_context_snapshot")
    op.drop_column("analysis_runs", "input_document_ids")
    op.drop_column("analysis_runs", "primary_document_id")
    op.drop_column("analysis_runs", "review_mode")

    op.drop_column("approved_checklists", "auto_approved")
    op.drop_column("approved_checklists", "vendor_context_snapshot")
    op.drop_column("approved_checklists", "input_document_ids")
    op.drop_column("approved_checklists", "profile_id")
    op.drop_column("approved_checklists", "review_mode")

    op.drop_column("checklist_draft_jobs", "vendor_context_snapshot")
    op.drop_column("checklist_draft_jobs", "input_document_ids")
    op.drop_column("checklist_draft_jobs", "profile_id")
    op.drop_column("checklist_draft_jobs", "review_mode")

    op.drop_index("document_chunks_document_page_idx", table_name="document_chunks")
    op.drop_column("document_chunks", "metadata_json")
    op.drop_column("document_chunks", "chunk_index")
    op.drop_column("document_chunks", "section_title")

    op.drop_index("documents_project_active_primary_uidx", table_name="documents")
    op.drop_index("documents_project_active_sort_idx", table_name="documents")
    op.drop_index("documents_project_primary_idx", table_name="documents")
    op.drop_index("documents_project_type_uploaded_idx", table_name="documents")
    op.drop_constraint("documents_source_kind_check", "documents", type_="check")
    op.drop_constraint("documents_document_type_check", "documents", type_="check")
    op.execute("DELETE FROM documents WHERE is_primary = false OR active = false OR deleted_at IS NOT NULL;")
    op.drop_column("documents", "deleted_at")
    op.drop_column("documents", "active")
    op.drop_column("documents", "sort_order")
    op.drop_column("documents", "uploaded_by")
    op.drop_column("documents", "source_url")
    op.drop_column("documents", "source_kind")
    op.drop_column("documents", "is_primary")
    op.drop_column("documents", "description")
    op.drop_column("documents", "display_name")
    op.drop_column("documents", "document_type")
    op.create_unique_constraint("documents_project_uidx", "documents", ["project_id"])

    op.drop_index("projects_tenant_recommendation_activity_idx", table_name="projects")
    op.drop_index("projects_tenant_vendor_name_idx", table_name="projects")
    op.drop_constraint("projects_current_recommendation_check", "projects", type_="check")
    op.drop_constraint("projects_vendor_region_check", "projects", type_="check")
    op.drop_constraint("projects_business_criticality_check", "projects", type_="check")
    op.drop_constraint("projects_review_type_check", "projects", type_="check")
    op.drop_column("projects", "context_completed_at")
    op.drop_column("projects", "current_recommendation")
    op.drop_column("projects", "current_approval_pack_id")
    op.drop_column("projects", "review_deadline")
    op.drop_column("projects", "internal_owner")
    op.drop_column("projects", "transfers_data_outside_eea")
    op.drop_column("projects", "processes_eu_personal_data")
    op.drop_column("projects", "vendor_region")
    op.drop_column("projects", "business_criticality")
    op.drop_column("projects", "has_ai_features")
    op.drop_column("projects", "shares_sensitive_data")
    op.drop_column("projects", "shares_employee_data")
    op.drop_column("projects", "shares_customer_data")
    op.drop_column("projects", "shares_personal_data")
    op.drop_column("projects", "data_types")
    op.drop_column("projects", "intended_use_case")
    op.drop_column("projects", "tool_or_service_name")
    op.drop_column("projects", "vendor_website")
    op.drop_column("projects", "vendor_name")
    op.drop_column("projects", "review_type")

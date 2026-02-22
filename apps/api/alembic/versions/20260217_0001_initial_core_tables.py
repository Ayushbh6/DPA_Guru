"""Initial core tables for DPA Analyzer V2 foundations.

Revision ID: 20260217_0001
Revises:
Create Date: 2026-02-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260217_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("region", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'ACTIVE'")),
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("storage_uri", sa.String(length=1024), nullable=False),
        sa.Column("uploaded_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("retention_expiry", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=False),
        sa.Column("page_end", sa.Integer(), nullable=False),
        sa.Column("provenance_id", sa.String(length=255), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.UniqueConstraint("document_id", "provenance_id", name="document_chunks_document_provenance_uidx"),
    )

    op.create_table(
        "analysis_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("model_version", sa.String(length=128), nullable=False),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
    )
    op.create_check_constraint(
        "analysis_runs_status_check",
        "analysis_runs",
        "status IN ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'PARTIAL_FAILURE')",
    )

    op.create_table(
        "findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id"), nullable=False),
        sa.Column("check_id", sa.String(length=128), nullable=False),
        sa.Column("category", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("risk", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("abstained", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("abstain_reason", sa.Text(), nullable=True),
        sa.Column("risk_rationale", sa.Text(), nullable=False),
        sa.Column("review_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("review_state", sa.String(length=32), nullable=False, server_default=sa.text("'PENDING'")),
        sa.UniqueConstraint("run_id", "check_id", name="findings_run_check_uidx"),
    )
    op.create_check_constraint(
        "findings_status_check",
        "findings",
        "status IN ('COMPLIANT', 'NON_COMPLIANT', 'PARTIAL', 'UNKNOWN')",
    )
    op.create_check_constraint("findings_risk_check", "findings", "risk IN ('LOW', 'MEDIUM', 'HIGH')")
    op.create_check_constraint(
        "findings_review_state_check",
        "findings",
        "review_state IN ('PENDING', 'APPROVED', 'REJECTED')",
    )

    op.create_table(
        "rule_hits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id"), nullable=False),
        sa.Column("rule_id", sa.String(length=128), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("matched_text", sa.Text(), nullable=False),
        sa.Column("page_ref", sa.String(length=64), nullable=False),
    )

    op.create_table(
        "review_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id"), nullable=False),
        sa.Column("finding_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("findings.id"), nullable=False),
        sa.Column("reviewer_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "billing_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False),
        sa.Column("amount_usd", sa.Float(), nullable=False),
        sa.Column("provider_ref", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("actor_type", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("event_name", sa.String(length=128), nullable=False),
        sa.Column("resource_type", sa.String(length=128), nullable=False),
        sa.Column("resource_id", sa.String(length=128), nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.execute(
        "CREATE INDEX documents_tenant_uploaded_idx ON documents (tenant_id, uploaded_at DESC);"
    )
    op.execute(
        "CREATE INDEX analysis_runs_tenant_status_started_idx ON analysis_runs (tenant_id, status, started_at DESC);"
    )
    op.create_index("rule_hits_run_severity_idx", "rule_hits", ["run_id", "severity"])
    op.execute(
        "CREATE INDEX review_actions_run_finding_created_idx ON review_actions (run_id, finding_id, created_at DESC);"
    )
    op.execute(
        "CREATE INDEX billing_events_tenant_created_idx ON billing_events (tenant_id, created_at DESC);"
    )
    op.execute(
        "CREATE INDEX audit_events_tenant_created_idx ON audit_events (tenant_id, created_at DESC);"
    )
    op.create_index("audit_events_trace_idx", "audit_events", ["trace_id"])

    op.execute("CREATE SCHEMA IF NOT EXISTS app;")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app.current_tenant_id()
        RETURNS uuid
        LANGUAGE sql
        STABLE
        AS $$
          SELECT NULLIF((current_setting('request.jwt.claims', true)::jsonb ->> 'tenant_id'), '')::uuid
        $$;
        """
    )

    for table_name in (
        "tenants",
        "users",
        "documents",
        "document_chunks",
        "analysis_runs",
        "findings",
        "rule_hits",
        "review_actions",
        "billing_events",
        "audit_events",
    ):
        op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;")

    op.execute(
        """
        CREATE POLICY tenants_tenant_isolation ON tenants
        FOR ALL TO authenticated
        USING (id = app.current_tenant_id())
        WITH CHECK (id = app.current_tenant_id());
        """
    )
    op.execute(
        """
        CREATE POLICY users_tenant_isolation ON users
        FOR ALL TO authenticated
        USING (tenant_id = app.current_tenant_id())
        WITH CHECK (tenant_id = app.current_tenant_id());
        """
    )
    op.execute(
        """
        CREATE POLICY documents_tenant_isolation ON documents
        FOR ALL TO authenticated
        USING (tenant_id = app.current_tenant_id())
        WITH CHECK (tenant_id = app.current_tenant_id());
        """
    )
    op.execute(
        """
        CREATE POLICY analysis_runs_tenant_isolation ON analysis_runs
        FOR ALL TO authenticated
        USING (tenant_id = app.current_tenant_id())
        WITH CHECK (tenant_id = app.current_tenant_id());
        """
    )
    op.execute(
        """
        CREATE POLICY billing_events_tenant_isolation ON billing_events
        FOR ALL TO authenticated
        USING (tenant_id = app.current_tenant_id())
        WITH CHECK (tenant_id = app.current_tenant_id());
        """
    )
    op.execute(
        """
        CREATE POLICY audit_events_tenant_isolation ON audit_events
        FOR ALL TO authenticated
        USING (tenant_id = app.current_tenant_id())
        WITH CHECK (tenant_id = app.current_tenant_id());
        """
    )
    op.execute(
        """
        CREATE POLICY document_chunks_tenant_isolation ON document_chunks
        FOR ALL TO authenticated
        USING (
          EXISTS (
            SELECT 1
            FROM documents d
            WHERE d.id = document_chunks.document_id
              AND d.tenant_id = app.current_tenant_id()
          )
        )
        WITH CHECK (
          EXISTS (
            SELECT 1
            FROM documents d
            WHERE d.id = document_chunks.document_id
              AND d.tenant_id = app.current_tenant_id()
          )
        );
        """
    )
    op.execute(
        """
        CREATE POLICY findings_tenant_isolation ON findings
        FOR ALL TO authenticated
        USING (
          EXISTS (
            SELECT 1
            FROM analysis_runs ar
            WHERE ar.id = findings.run_id
              AND ar.tenant_id = app.current_tenant_id()
          )
        )
        WITH CHECK (
          EXISTS (
            SELECT 1
            FROM analysis_runs ar
            WHERE ar.id = findings.run_id
              AND ar.tenant_id = app.current_tenant_id()
          )
        );
        """
    )
    op.execute(
        """
        CREATE POLICY rule_hits_tenant_isolation ON rule_hits
        FOR ALL TO authenticated
        USING (
          EXISTS (
            SELECT 1
            FROM analysis_runs ar
            WHERE ar.id = rule_hits.run_id
              AND ar.tenant_id = app.current_tenant_id()
          )
        )
        WITH CHECK (
          EXISTS (
            SELECT 1
            FROM analysis_runs ar
            WHERE ar.id = rule_hits.run_id
              AND ar.tenant_id = app.current_tenant_id()
          )
        );
        """
    )
    op.execute(
        """
        CREATE POLICY review_actions_tenant_isolation ON review_actions
        FOR ALL TO authenticated
        USING (
          EXISTS (
            SELECT 1
            FROM analysis_runs ar
            WHERE ar.id = review_actions.run_id
              AND ar.tenant_id = app.current_tenant_id()
          )
        )
        WITH CHECK (
          EXISTS (
            SELECT 1
            FROM analysis_runs ar
            WHERE ar.id = review_actions.run_id
              AND ar.tenant_id = app.current_tenant_id()
          )
        );
        """
    )


def downgrade() -> None:
    for policy_name, table_name in (
        ("review_actions_tenant_isolation", "review_actions"),
        ("rule_hits_tenant_isolation", "rule_hits"),
        ("findings_tenant_isolation", "findings"),
        ("document_chunks_tenant_isolation", "document_chunks"),
        ("audit_events_tenant_isolation", "audit_events"),
        ("billing_events_tenant_isolation", "billing_events"),
        ("analysis_runs_tenant_isolation", "analysis_runs"),
        ("documents_tenant_isolation", "documents"),
        ("users_tenant_isolation", "users"),
        ("tenants_tenant_isolation", "tenants"),
    ):
        op.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table_name};")

    op.execute("DROP FUNCTION IF EXISTS app.current_tenant_id;")
    op.execute("DROP SCHEMA IF EXISTS app CASCADE;")

    op.drop_index("audit_events_trace_idx", table_name="audit_events")
    op.drop_index("audit_events_tenant_created_idx", table_name="audit_events")
    op.drop_index("billing_events_tenant_created_idx", table_name="billing_events")
    op.drop_index("review_actions_run_finding_created_idx", table_name="review_actions")
    op.drop_index("rule_hits_run_severity_idx", table_name="rule_hits")
    op.drop_index("analysis_runs_tenant_status_started_idx", table_name="analysis_runs")
    op.drop_index("documents_tenant_uploaded_idx", table_name="documents")

    op.drop_table("audit_events")
    op.drop_table("billing_events")
    op.drop_table("review_actions")
    op.drop_table("rule_hits")
    op.drop_table("findings")
    op.drop_table("analysis_runs")
    op.drop_table("document_chunks")
    op.drop_table("documents")
    op.drop_table("users")
    op.drop_table("tenants")

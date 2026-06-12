from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from docker.errors import APIError, DockerException, ImageNotFound
from testcontainers.postgres import PostgresContainer

REPO_ROOT = Path(__file__).resolve().parents[3]


def _to_psycopg_url(connection_url: str) -> str:
    return connection_url.replace("postgresql+psycopg2://", "postgresql+psycopg://")


def _alembic_config(database_url: str) -> Config:
    cfg = Config(str(REPO_ROOT / "apps" / "api" / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "apps" / "api" / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def test_alembic_upgrade_and_downgrade_smoke() -> None:
    try:
        with PostgresContainer("pgvector/pgvector:pg16") as postgres:
            database_url = _to_psycopg_url(postgres.get_connection_url())
            alembic_cfg = _alembic_config(database_url)

            # Local/test Postgres containers don't include Supabase-style roles by default.
            bootstrap_engine = sa.create_engine(database_url, future=True)
            with bootstrap_engine.begin() as bootstrap_conn:
                bootstrap_conn.execute(sa.text("DO $$ BEGIN CREATE ROLE authenticated NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;"))
            bootstrap_engine.dispose()

            command.upgrade(alembic_cfg, "head")

            engine = sa.create_engine(database_url, future=True)
            with engine.begin() as conn:
                expected_tables = {
                    "tenants",
                    "users",
                    "projects",
                    "documents",
                    "document_artifacts",
                    "document_parse_jobs",
                    "checklist_draft_jobs",
                    "checklist_synthesis_runs",
                    "checklist_synthesis_events",
                    "approved_checklists",
                    "document_chunks",
                    "analysis_runs",
                    "analysis_reports",
                    "analysis_run_documents",
                    "approval_packs",
                    "approval_pack_stage_outputs",
                    "approval_pack_revisions",
                    "agent_runs",
                    "agent_run_messages",
                    "agent_run_tool_calls",
                    "agent_run_outputs",
                    "agent_run_events",
                    "agent_run_artifacts",
                    "findings",
                    "rule_hits",
                    "review_actions",
                    "billing_events",
                    "audit_events",
                    "kb_sources",
                    "kb_ingest_runs",
                    "kb_ingest_tasks",
                    "kb_chunks",
                }
                absent_tables = {
                    "registry_audit_events",
                    "registry_checklist_synthesis_runs",
                    "registry_diffs",
                    "registry_extracted_obligations",
                    "registry_extraction_chunks",
                    "registry_extraction_runs",
                    "registry_extraction_segments",
                    "registry_snapshots",
                    "registry_sources",
                    "checklist_approvals",
                    "checklist_item_sources",
                    "checklist_items",
                    "checklist_reviews",
                    "checklist_versions",
                }
                table_names = set(
                    conn.execute(
                        sa.text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                    ).scalars()
                )
                assert expected_tables.issubset(table_names)
                assert absent_tables.isdisjoint(table_names)

                idx_names = set(
                    conn.execute(
                        sa.text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
                    ).scalars()
                )
                assert "documents_tenant_uploaded_idx" in idx_names
                assert "projects_tenant_last_activity_idx" in idx_names
                assert "projects_status_updated_idx" in idx_names
                assert "projects_owner_status_updated_idx" in idx_names
                assert "projects_deleted_purge_idx" in idx_names
                assert "analysis_runs_tenant_status_started_idx" in idx_names
                assert "rule_hits_run_severity_idx" in idx_names
                assert "review_actions_run_finding_created_idx" in idx_names
                assert "billing_events_tenant_created_idx" in idx_names
                assert "audit_events_tenant_created_idx" in idx_names
                assert "audit_events_trace_idx" in idx_names
                assert "document_chunks_document_provenance_uidx" in idx_names
                assert "findings_run_check_uidx" in idx_names
                assert "kb_ingest_runs_status_created_idx" in idx_names
                assert "kb_ingest_tasks_run_final_idx" in idx_names
                assert "kb_chunks_source_idx" in idx_names
                assert "checklist_draft_jobs_tenant_created_idx" in idx_names
                assert "checklist_draft_jobs_document_created_idx" in idx_names
                assert "checklist_draft_jobs_status_updated_idx" in idx_names
                assert "document_artifacts_document_type_created_idx" in idx_names
                assert "document_artifacts_tenant_created_idx" in idx_names
                assert "document_parse_jobs_project_created_idx" in idx_names
                assert "checklist_draft_jobs_project_created_idx" in idx_names
                assert "checklist_synthesis_runs_draft_started_idx" in idx_names
                assert "checklist_synthesis_events_run_created_idx" in idx_names
                assert "analysis_runs_project_started_idx" in idx_names
                assert "approved_checklists_project_created_idx" in idx_names
                assert "analysis_runs_status_started_idx" in idx_names
                assert "documents_project_active_primary_uidx" in idx_names
                assert "documents_project_type_uploaded_idx" in idx_names
                assert "document_chunks_document_page_idx" in idx_names
                assert "analysis_run_documents_run_document_uidx" in idx_names
                assert "approval_packs_project_created_idx" in idx_names
                assert "approval_packs_project_active_idx" in idx_names
                assert "agent_runs_project_created_idx" in idx_names
                assert "agent_runs_tenant_idempotency_uidx" in idx_names
                assert "agent_run_messages_run_sequence_uidx" in idx_names
                assert "agent_run_tool_calls_run_sequence_uidx" in idx_names
                assert "agent_run_outputs_run_type_idx" in idx_names
                assert "agent_run_events_run_sequence_uidx" in idx_names
                assert "agent_run_artifacts_run_type_created_idx" in idx_names
                assert "approval_pack_stage_outputs_pack_stage_idx" in idx_names
                assert "approval_pack_revisions_pack_created_idx" in idx_names

                rls_rows = conn.execute(
                    sa.text(
                        """
                        SELECT relname, relrowsecurity
                        FROM pg_class
                        WHERE relname IN (
                          'tenants', 'users', 'documents', 'document_chunks',
                          'document_artifacts',
                          'projects', 'document_parse_jobs', 'checklist_draft_jobs', 'analysis_runs', 'findings', 'rule_hits',
                          'review_actions', 'billing_events', 'audit_events', 'checklist_synthesis_runs', 'checklist_synthesis_events',
                          'analysis_run_documents', 'approval_packs', 'approval_pack_stage_outputs', 'approval_pack_revisions',
                          'agent_runs', 'agent_run_messages', 'agent_run_tool_calls', 'agent_run_outputs', 'agent_run_events',
                          'agent_run_artifacts'
                        )
                        """
                    )
                ).all()
                assert all(row.relrowsecurity for row in rls_rows)

                embedding_type = conn.execute(
                    sa.text(
                        """
                        SELECT format_type(a.atttypid, a.atttypmod)
                        FROM pg_attribute a
                        JOIN pg_class c ON a.attrelid = c.oid
                        WHERE c.relname = 'document_chunks'
                          AND a.attname = 'embedding'
                          AND a.attnum > 0
                        """
                    )
                ).scalar_one()
                assert embedding_type == "vector(1536)"
                kb_embedding_type = conn.execute(
                    sa.text(
                        """
                        SELECT format_type(a.atttypid, a.atttypmod)
                        FROM pg_attribute a
                        JOIN pg_class c ON a.attrelid = c.oid
                        WHERE c.relname = 'kb_chunks'
                          AND a.attname = 'embedding'
                          AND a.attnum > 0
                        """
                    )
                ).scalar_one()
                assert kb_embedding_type == "vector(1536)"

                tenant_id = conn.execute(
                    sa.text(
                        """
                        INSERT INTO tenants (name, region, status)
                        VALUES (:name, :region, :status)
                        RETURNING id
                        """
                    ),
                    {"name": "Acme", "region": "eu-west-1", "status": "ACTIVE"},
                ).scalar_one()

                user_id = conn.execute(
                    sa.text(
                        """
                        INSERT INTO users (tenant_id, email, role)
                        VALUES (:tenant_id, :email, :role)
                        RETURNING id
                        """
                    ),
                    {"tenant_id": tenant_id, "email": "reviewer@example.com", "role": "REVIEWER"},
                ).scalar_one()

                project_id = conn.execute(
                    sa.text(
                        """
                        INSERT INTO projects (tenant_id, owner_username, name, status)
                        VALUES (:tenant_id, :owner_username, :name, :status)
                        RETURNING id
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "owner_username": "local-dev",
                        "name": "Untitled analysis",
                        "status": "EMPTY",
                    },
                ).scalar_one()

                conn.execute(
                    sa.text(
                        """
                        UPDATE projects
                        SET status = :status
                        WHERE id = :project_id
                        """
                    ),
                    {"status": "DELETED", "project_id": project_id},
                )

                deleted_status = conn.execute(
                    sa.text("SELECT status FROM projects WHERE id = :project_id"),
                    {"project_id": project_id},
                ).scalar_one()
                assert deleted_status == "DELETED"

                conn.execute(
                    sa.text(
                        """
                        UPDATE projects
                        SET status = :status
                        WHERE id = :project_id
                        """
                    ),
                    {"status": "EMPTY", "project_id": project_id},
                )

                document_id = conn.execute(
                    sa.text(
                        """
                        INSERT INTO documents (
                          tenant_id, project_id, filename, mime_type, page_count, storage_uri,
                          document_type, is_primary, uploaded_by
                        )
                        VALUES (
                          :tenant_id, :project_id, :filename, :mime_type, :page_count, :storage_uri,
                          :document_type, :is_primary, :uploaded_by
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "filename": "sample-dpa.pdf",
                        "mime_type": "application/pdf",
                        "page_count": 12,
                        "storage_uri": "supabase://bucket/path/sample-dpa.pdf",
                        "document_type": "main_dpa",
                        "is_primary": True,
                        "uploaded_by": "local-dev",
                    },
                ).scalar_one()

                support_document_id = conn.execute(
                    sa.text(
                        """
                        INSERT INTO documents (
                          tenant_id, project_id, filename, mime_type, page_count, storage_uri,
                          document_type, is_primary, uploaded_by
                        )
                        VALUES (
                          :tenant_id, :project_id, :filename, :mime_type, :page_count, :storage_uri,
                          :document_type, false, :uploaded_by
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "filename": "subprocessors.pdf",
                        "mime_type": "application/pdf",
                        "page_count": 3,
                        "storage_uri": "supabase://bucket/path/subprocessors.pdf",
                        "document_type": "subprocessors",
                        "uploaded_by": "local-dev",
                    },
                ).scalar_one()

                artifact_id = conn.execute(
                    sa.text(
                        """
                        INSERT INTO document_artifacts (
                          tenant_id, project_id, document_id, artifact_type, storage_provider, bucket,
                          object_key, object_uri, content_type, byte_size, sha256, active
                        )
                        VALUES (
                          :tenant_id, :project_id, :document_id, :artifact_type, :storage_provider, :bucket,
                          :object_key, :object_uri, :content_type, :byte_size, :sha256, :active
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "document_id": document_id,
                        "artifact_type": "SOURCE_PDF",
                        "storage_provider": "r2",
                        "bucket": "docs",
                        "object_key": "tenants/acme/projects/demo/documents/sample/source/original.pdf",
                        "object_uri": "r2://docs/tenants/acme/projects/demo/documents/sample/source/original.pdf",
                        "content_type": "application/pdf",
                        "byte_size": 1024,
                        "sha256": "f" * 64,
                        "active": True,
                    },
                ).scalar_one()
                assert artifact_id is not None

                run_id = conn.execute(
                    sa.text(
                        """
                        INSERT INTO analysis_runs (
                          tenant_id, project_id, document_id, primary_document_id, input_document_ids,
                          status, model_version, policy_version
                        )
                        VALUES (
                          :tenant_id, :project_id, :document_id, :primary_document_id, CAST(:input_document_ids AS jsonb),
                          :status, :model_version, :policy_version
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "document_id": document_id,
                        "primary_document_id": document_id,
                        "input_document_ids": f'["{document_id}", "{support_document_id}"]',
                        "status": "QUEUED",
                        "model_version": "managed-1.0",
                        "policy_version": "policy-2026-02-16",
                    },
                ).scalar_one()

                conn.execute(
                    sa.text(
                        """
                        INSERT INTO analysis_run_documents (
                          tenant_id, project_id, analysis_run_id, document_id, document_type, role
                        )
                        VALUES
                          (:tenant_id, :project_id, :run_id, :document_id, 'main_dpa', 'primary'),
                          (:tenant_id, :project_id, :run_id, :support_document_id, 'subprocessors', 'supporting')
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "run_id": run_id,
                        "document_id": document_id,
                        "support_document_id": support_document_id,
                    },
                )

                finding_id = conn.execute(
                    sa.text(
                        """
                        INSERT INTO findings (
                          run_id, check_id, category, status, risk, confidence, abstained, risk_rationale
                        )
                        VALUES (
                          :run_id, :check_id, :category, :status, :risk, :confidence, :abstained, :risk_rationale
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "run_id": run_id,
                        "check_id": "CHECK_001",
                        "category": "Instructions",
                        "status": "PARTIAL",
                        "risk": "HIGH",
                        "confidence": 0.91,
                        "abstained": False,
                        "risk_rationale": "Instruction language contains broad carve-outs.",
                    },
                ).scalar_one()

                conn.execute(
                    sa.text(
                        """
                        INSERT INTO review_actions (run_id, finding_id, reviewer_user_id, action, comment)
                        VALUES (:run_id, :finding_id, :reviewer_user_id, :action, :comment)
                        """
                    ),
                    {
                        "run_id": run_id,
                        "finding_id": finding_id,
                        "reviewer_user_id": user_id,
                        "action": "FLAGGED",
                        "comment": "Needs legal follow-up",
                    },
                )

                approval_pack_id = conn.execute(
                    sa.text(
                        """
                        INSERT INTO approval_packs (
                          tenant_id, project_id, analysis_run_id, version, status, recommendation,
                          recommendation_summary, confidence, review_required, pack_json, generated_by
                        )
                        VALUES (
                          :tenant_id, :project_id, :run_id, 'approval_pack_v1', 'draft', 'escalate',
                          'Escalate due to broad instruction carve-outs.', 0.82, true,
                          CAST(:pack_json AS jsonb), 'system'
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "run_id": run_id,
                        "pack_json": '{"recommendation":"escalate","evidence":[]}',
                    },
                ).scalar_one()

                agent_run_id = conn.execute(
                    sa.text(
                        """
                        INSERT INTO agent_runs (
                          tenant_id, project_id, analysis_run_id, approval_pack_id,
                          agent_name, agent_role, agent_version, status, model_provider,
                          model_name, input_tokens, output_tokens, total_tokens
                        )
                        VALUES (
                          :tenant_id, :project_id, :run_id, :approval_pack_id,
                          'recommendation-agent', 'recommendation', 'v1', 'completed', 'google',
                          'gemini-test', 100, 50, 150
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "run_id": run_id,
                        "approval_pack_id": approval_pack_id,
                    },
                ).scalar_one()

                conn.execute(
                    sa.text(
                        """
                        INSERT INTO agent_run_messages (tenant_id, agent_run_id, sequence_no, role, content)
                        VALUES
                          (:tenant_id, :agent_run_id, 1, 'system', 'You are the recommendation agent.'),
                          (:tenant_id, :agent_run_id, 2, 'user', 'Assess the approval recommendation.')
                        """
                    ),
                    {"tenant_id": tenant_id, "agent_run_id": agent_run_id},
                )
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO agent_run_tool_calls (
                          tenant_id, agent_run_id, sequence_no, tool_name, input_json, output_json, status
                        )
                        VALUES (
                          :tenant_id, :agent_run_id, 1, 'search_uploaded_docs',
                          CAST(:input_json AS jsonb), CAST(:output_json AS jsonb), 'completed'
                        )
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "agent_run_id": agent_run_id,
                        "input_json": '{"query":"instructions"}',
                        "output_json": '{"hits":1}',
                    },
                )
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO agent_run_outputs (
                          tenant_id, agent_run_id, output_type, schema_version, output_json, validation_status
                        )
                        VALUES (
                          :tenant_id, :agent_run_id, 'RecommendationOutput', 'v1',
                          CAST(:output_json AS jsonb), 'valid'
                        )
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "agent_run_id": agent_run_id,
                        "output_json": '{"recommendation":"escalate","confidence":0.82}',
                    },
                )
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO agent_run_events (tenant_id, agent_run_id, sequence_no, event_type, payload_json)
                        VALUES (:tenant_id, :agent_run_id, 1, 'completed', CAST(:payload_json AS jsonb))
                        """
                    ),
                    {"tenant_id": tenant_id, "agent_run_id": agent_run_id, "payload_json": '{"ok":true}'},
                )
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO agent_run_artifacts (
                          tenant_id, agent_run_id, artifact_type, storage_provider, object_uri, content_type
                        )
                        VALUES (:tenant_id, :agent_run_id, 'raw_response', 'local', 'memory://raw-response', 'application/json')
                        """
                    ),
                    {"tenant_id": tenant_id, "agent_run_id": agent_run_id},
                )
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO approval_pack_stage_outputs (
                          tenant_id, project_id, analysis_run_id, approval_pack_id, agent_run_id,
                          stage_name, stage_version, output_json, status
                        )
                        VALUES (
                          :tenant_id, :project_id, :run_id, :approval_pack_id, :agent_run_id,
                          'recommendation', 'v1', CAST(:output_json AS jsonb), 'completed'
                        )
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "run_id": run_id,
                        "approval_pack_id": approval_pack_id,
                        "agent_run_id": agent_run_id,
                        "output_json": '{"recommendation":"escalate"}',
                    },
                )
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO approval_pack_revisions (
                          tenant_id, project_id, approval_pack_id, created_by_type, created_by,
                          reason, changes_summary, patch_json, status
                        )
                        VALUES (
                          :tenant_id, :project_id, :approval_pack_id, 'user', 'local-dev',
                          'Test revision', 'Clarified recommendation summary', CAST(:patch_json AS jsonb), 'proposed'
                        )
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "approval_pack_id": approval_pack_id,
                        "patch_json": '[{"op":"replace","path":"/recommendationSummary","value":"Escalate."}]',
                    },
                )

                reconstructed_counts = conn.execute(
                    sa.text(
                        """
                        SELECT
                          (SELECT count(*) FROM agent_run_messages WHERE agent_run_id = :agent_run_id) AS messages,
                          (SELECT count(*) FROM agent_run_tool_calls WHERE agent_run_id = :agent_run_id) AS tool_calls,
                          (SELECT count(*) FROM agent_run_outputs WHERE agent_run_id = :agent_run_id) AS outputs,
                          (SELECT count(*) FROM agent_run_events WHERE agent_run_id = :agent_run_id) AS events,
                          (SELECT count(*) FROM agent_run_artifacts WHERE agent_run_id = :agent_run_id) AS artifacts
                        """
                    ),
                    {"agent_run_id": agent_run_id},
                ).one()
                assert reconstructed_counts == (2, 1, 1, 1, 1)

                conn.execute(sa.text("SET enable_seqscan = off;"))
                explain_plan = "\n".join(
                    conn.execute(
                        sa.text(
                            """
                            EXPLAIN (FORMAT TEXT)
                            SELECT id
                            FROM analysis_runs
                            WHERE tenant_id = :tenant_id AND status = 'QUEUED'
                            """
                        ),
                        {"tenant_id": tenant_id},
                    ).scalars()
                )
                assert "Index Scan" in explain_plan or "Bitmap Heap Scan" in explain_plan
                assert (
                    "analysis_runs_tenant_status_started_idx" in explain_plan
                    or "analysis_runs_status_started_idx" in explain_plan
                )

                kb_source_id = conn.execute(
                    sa.text(
                        """
                        INSERT INTO kb_sources (
                          source_id, title, authority, source_kind, source_url, local_txt_path, local_md_path,
                          content_sha256, char_count, token_count, active
                        )
                        VALUES (
                          :source_id, :title, :authority, :source_kind, :source_url, :local_txt_path, :local_md_path,
                          :content_sha256, :char_count, :token_count, :active
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "source_id": "gdpr_regulation_2016_679",
                        "title": "GDPR",
                        "authority": "EUR-Lex",
                        "source_kind": "HTML",
                        "source_url": "https://example.com/gdpr",
                        "local_txt_path": "kb/gdpr/content.txt",
                        "local_md_path": "kb/gdpr/content.md",
                        "content_sha256": "c" * 64,
                        "char_count": 1234,
                        "token_count": 456,
                        "active": True,
                    },
                ).scalar_one()
                assert kb_source_id is not None

                kb_run_id = conn.execute(
                    sa.text(
                        """
                        INSERT INTO kb_ingest_runs (
                          id, status, kb_manifest_sha256, chunk_size, chunk_overlap, full_doc_threshold,
                          llm_model, embedding_model, llm_concurrency, embed_concurrency, upsert_concurrency,
                          request_retries, total_chunks
                        )
                        VALUES (
                          gen_random_uuid(), :status, :kb_manifest_sha256, :chunk_size, :chunk_overlap, :full_doc_threshold,
                          :llm_model, :embedding_model, :llm_concurrency, :embed_concurrency, :upsert_concurrency,
                          :request_retries, :total_chunks
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "status": "RUNNING",
                        "kb_manifest_sha256": "d" * 64,
                        "chunk_size": 800,
                        "chunk_overlap": 300,
                        "full_doc_threshold": 50000,
                        "llm_model": "test-llm",
                        "embedding_model": "test-embed",
                        "llm_concurrency": 2,
                        "embed_concurrency": 2,
                        "upsert_concurrency": 2,
                        "request_retries": 1,
                        "total_chunks": 1,
                    },
                ).scalar_one()

                kb_task_id = conn.execute(
                    sa.text(
                        """
                        INSERT INTO kb_ingest_tasks (
                          id, run_id, source_id, chunk_index, chunk_count, raw_text, raw_text_sha256,
                          chunk_token_count, doc_token_count, context_mode, context_window_start, context_window_end,
                          context_text, llm_status, embed_status, upsert_status, final_status,
                          structured_json, structured_text, embedding_dim, embedding
                        )
                        VALUES (
                          gen_random_uuid(), :run_id, :source_id, :chunk_index, :chunk_count, :raw_text, :raw_text_sha256,
                          :chunk_token_count, :doc_token_count, :context_mode, :context_window_start, :context_window_end,
                          :context_text, 'SUCCEEDED', 'SUCCEEDED', 'PENDING', 'PENDING',
                          CAST(:structured_json AS jsonb), :structured_text, 1536, CAST(:embedding AS vector)
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "run_id": kb_run_id,
                        "source_id": "gdpr_regulation_2016_679",
                        "chunk_index": 0,
                        "chunk_count": 1,
                        "raw_text": "Article 28 processor obligations",
                        "raw_text_sha256": "e" * 64,
                        "chunk_token_count": 10,
                        "doc_token_count": 100,
                        "context_mode": "FULL_DOC",
                        "context_window_start": 0,
                        "context_window_end": 0,
                        "context_text": "Article 28 processor obligations",
                        "structured_json": '{"source_title":"GDPR","source_url":"https://example.com/gdpr","article_no":"Article 28","short_description":"Processor clauses","consequences":null,"possible_reasons":["Missing instruction clause"],"citation_quote":"processor obligations","citation_section":"Article 28"}',
                        "structured_text": '{"article_no":"Article 28"}',
                        "embedding": "[" + ",".join(["0.0"] * 1536) + "]",
                    },
                ).scalar_one()

                conn.execute(
                    sa.text(
                        """
                        INSERT INTO kb_chunks (
                          source_id, source_title, source_url, chunk_index, chunk_count, chunk_token_count, doc_token_count,
                          context_mode, context_window_start, context_window_end, raw_text, structured_json, structured_text,
                          combined_text, raw_text_sha256, llm_model, embedding_model, embedding
                        )
                        VALUES (
                          :source_id, :source_title, :source_url, :chunk_index, :chunk_count, :chunk_token_count, :doc_token_count,
                          :context_mode, :context_window_start, :context_window_end, :raw_text, CAST(:structured_json AS jsonb), :structured_text,
                          :combined_text, :raw_text_sha256, :llm_model, :embedding_model, CAST(:embedding AS vector)
                        )
                        """
                    ),
                    {
                        "source_id": "gdpr_regulation_2016_679",
                        "source_title": "GDPR",
                        "source_url": "https://example.com/gdpr",
                        "chunk_index": 0,
                        "chunk_count": 1,
                        "chunk_token_count": 10,
                        "doc_token_count": 100,
                        "context_mode": "FULL_DOC",
                        "context_window_start": 0,
                        "context_window_end": 0,
                        "raw_text": "Article 28 processor obligations",
                        "structured_json": '{"source_title":"GDPR","source_url":"https://example.com/gdpr","article_no":"Article 28","short_description":"Processor clauses","consequences":null,"possible_reasons":["Missing instruction clause"],"citation_quote":"processor obligations","citation_section":"Article 28"}',
                        "structured_text": '{"article_no":"Article 28"}',
                        "combined_text": "## RAW_TEXT_CHUNK\\nArticle 28 processor obligations",
                        "raw_text_sha256": "e" * 64,
                        "llm_model": "test-llm",
                        "embedding_model": "test-embed",
                        "embedding": "[" + ",".join(["0.0"] * 1536) + "]",
                    },
                )
                assert kb_task_id is not None

            command.downgrade(alembic_cfg, "base")

            with engine.connect() as conn:
                remaining_tables = set(
                    conn.execute(
                        sa.text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                    ).scalars()
                )
                assert "analysis_runs" not in remaining_tables
                assert "tenants" not in remaining_tables

            engine.dispose()
    except (DockerException, APIError, ImageNotFound) as exc:
        pytest.skip(f"Docker or pgvector image unavailable for migration smoke test: {exc}")

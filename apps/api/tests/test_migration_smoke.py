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

            command.upgrade(alembic_cfg, "head")

            engine = sa.create_engine(database_url, future=True)
            with engine.begin() as conn:
                expected_tables = {
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
                    "registry_sources",
                    "registry_snapshots",
                    "registry_diffs",
                    "checklist_versions",
                    "checklist_items",
                    "checklist_item_sources",
                    "checklist_reviews",
                    "checklist_approvals",
                    "registry_audit_events",
                }
                table_names = set(
                    conn.execute(
                        sa.text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                    ).scalars()
                )
                assert expected_tables.issubset(table_names)

                idx_names = set(
                    conn.execute(
                        sa.text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
                    ).scalars()
                )
                assert "documents_tenant_uploaded_idx" in idx_names
                assert "analysis_runs_tenant_status_started_idx" in idx_names
                assert "rule_hits_run_severity_idx" in idx_names
                assert "review_actions_run_finding_created_idx" in idx_names
                assert "billing_events_tenant_created_idx" in idx_names
                assert "audit_events_tenant_created_idx" in idx_names
                assert "audit_events_trace_idx" in idx_names
                assert "document_chunks_document_provenance_uidx" in idx_names
                assert "findings_run_check_uidx" in idx_names
                assert "registry_snapshots_source_lang_fetched_idx" in idx_names
                assert "registry_diffs_source_lang_created_idx" in idx_names
                assert "checklist_items_version_check_idx" in idx_names
                assert "checklist_versions_single_active_idx" in idx_names
                assert "registry_audit_events_trace_idx" in idx_names

                rls_rows = conn.execute(
                    sa.text(
                        """
                        SELECT relname, relrowsecurity
                        FROM pg_class
                        WHERE relname IN (
                          'tenants', 'users', 'documents', 'document_chunks',
                          'analysis_runs', 'findings', 'rule_hits',
                          'review_actions', 'billing_events', 'audit_events'
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

                document_id = conn.execute(
                    sa.text(
                        """
                        INSERT INTO documents (tenant_id, filename, mime_type, page_count, storage_uri)
                        VALUES (:tenant_id, :filename, :mime_type, :page_count, :storage_uri)
                        RETURNING id
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "filename": "sample-dpa.pdf",
                        "mime_type": "application/pdf",
                        "page_count": 12,
                        "storage_uri": "supabase://bucket/path/sample-dpa.pdf",
                    },
                ).scalar_one()

                run_id = conn.execute(
                    sa.text(
                        """
                        INSERT INTO analysis_runs (tenant_id, document_id, status, model_version, policy_version)
                        VALUES (:tenant_id, :document_id, :status, :model_version, :policy_version)
                        RETURNING id
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "document_id": document_id,
                        "status": "QUEUED",
                        "model_version": "managed-1.0",
                        "policy_version": "policy-2026-02-16",
                    },
                ).scalar_one()

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
                assert "analysis_runs_tenant_status_started_idx" in explain_plan

                registry_source_id = conn.execute(
                    sa.text(
                        """
                        INSERT INTO registry_sources (
                          source_id, authority, celex_or_doc_id, source_type,
                          languages, status_rule, fetch_url_map, enabled
                        )
                        VALUES (
                          :source_id, :authority, :celex_or_doc_id, :source_type,
                          :languages, :status_rule, :fetch_url_map::jsonb, :enabled
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "source_id": "gdpr_regulation_2016_679",
                        "authority": "EUR-Lex",
                        "celex_or_doc_id": "32016R0679",
                        "source_type": "LAW",
                        "languages": ["EN", "FR", "DE"],
                        "status_rule": "IN_FORCE_FINAL_ONLY",
                        "fetch_url_map": '{"EN":"https://example.com/en","FR":"https://example.com/fr","DE":"https://example.com/de"}',
                        "enabled": True,
                    },
                ).scalar_one()

                snapshot_id_1 = conn.execute(
                    sa.text(
                        """
                        INSERT INTO registry_snapshots (
                          registry_source_id, source_id, language, sha256,
                          raw_storage_path, parsed_storage_path, parse_status,
                          normalized_text, tracked_sections, metadata
                        )
                        VALUES (
                          :registry_source_id, :source_id, :language, :sha256,
                          :raw_storage_path, :parsed_storage_path, :parse_status,
                          :normalized_text, :tracked_sections::jsonb, :metadata::jsonb
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "registry_source_id": registry_source_id,
                        "source_id": "gdpr_regulation_2016_679",
                        "language": "EN",
                        "sha256": "a" * 64,
                        "raw_storage_path": "supabase://legal-source-raw/gdpr/one.raw",
                        "parsed_storage_path": "supabase://legal-source-parsed/gdpr/one.txt",
                        "parse_status": "PARSED",
                        "normalized_text": "Article 28 old text",
                        "tracked_sections": '["Article 28 old text"]',
                        "metadata": '{"source_url":"https://example.com/en"}',
                    },
                ).scalar_one()

                snapshot_id_2 = conn.execute(
                    sa.text(
                        """
                        INSERT INTO registry_snapshots (
                          registry_source_id, source_id, language, sha256,
                          raw_storage_path, parsed_storage_path, parse_status,
                          normalized_text, tracked_sections, metadata
                        )
                        VALUES (
                          :registry_source_id, :source_id, :language, :sha256,
                          :raw_storage_path, :parsed_storage_path, :parse_status,
                          :normalized_text, :tracked_sections::jsonb, :metadata::jsonb
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "registry_source_id": registry_source_id,
                        "source_id": "gdpr_regulation_2016_679",
                        "language": "EN",
                        "sha256": "b" * 64,
                        "raw_storage_path": "supabase://legal-source-raw/gdpr/two.raw",
                        "parsed_storage_path": "supabase://legal-source-parsed/gdpr/two.txt",
                        "parse_status": "PARSED",
                        "normalized_text": "Article 28 changed text",
                        "tracked_sections": '["Article 28 changed text"]',
                        "metadata": '{"source_url":"https://example.com/en"}',
                    },
                ).scalar_one()

                conn.execute(
                    sa.text(
                        """
                        INSERT INTO registry_diffs (
                          registry_source_id, source_id, language, from_snapshot_id,
                          to_snapshot_id, change_class, summary, changed_sections, token_change_ratio
                        )
                        VALUES (
                          :registry_source_id, :source_id, :language, :from_snapshot_id,
                          :to_snapshot_id, :change_class, :summary, :changed_sections::jsonb, :token_change_ratio
                        )
                        """
                    ),
                    {
                        "registry_source_id": registry_source_id,
                        "source_id": "gdpr_regulation_2016_679",
                        "language": "EN",
                        "from_snapshot_id": snapshot_id_1,
                        "to_snapshot_id": snapshot_id_2,
                        "change_class": "MATERIAL_CHANGE",
                        "summary": "Material legal change.",
                        "changed_sections": '["Article 28 changed text"]',
                        "token_change_ratio": 0.45,
                    },
                )

                checklist_version_id = conn.execute(
                    sa.text(
                        """
                        INSERT INTO checklist_versions (
                          version_id, status, is_active, policy_version, generated_from_snapshot_set,
                          governance, checklist_json, created_by
                        )
                        VALUES (
                          :version_id, :status, :is_active, :policy_version, :generated_from_snapshot_set::jsonb,
                          :governance::jsonb, :checklist_json::jsonb, :created_by
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "version_id": "checklist_20260217_190000",
                        "status": "ACTIVE",
                        "is_active": True,
                        "policy_version": "policy-2026-02-17",
                        "generated_from_snapshot_set": f'["{snapshot_id_2}"]',
                        "governance": '{"owner":"Policy Team","approval_status":"REVIEWED","policy_version":"policy-2026-02-17"}',
                        "checklist_json": '{"version":"official_v1","governance":{"owner":"Policy Team","approval_status":"REVIEWED","policy_version":"policy-2026-02-17"},"checks":[]}',
                        "created_by": "registry-operator",
                    },
                ).scalar_one()

                checklist_item_id = conn.execute(
                    sa.text(
                        """
                        INSERT INTO checklist_items (
                          checklist_version_id, check_id, title, category, legal_basis, required,
                          severity, evidence_hint, pass_criteria, fail_criteria, sort_order
                        )
                        VALUES (
                          :checklist_version_id, :check_id, :title, :category, :legal_basis::jsonb, :required,
                          :severity, :evidence_hint, :pass_criteria::jsonb, :fail_criteria::jsonb, :sort_order
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "checklist_version_id": checklist_version_id,
                        "check_id": "CHECK_001",
                        "title": "Instruction limitation",
                        "category": "Instructions",
                        "legal_basis": '["Policy Section 1"]',
                        "required": True,
                        "severity": "MANDATORY",
                        "evidence_hint": "Find instruction clause",
                        "pass_criteria": '["clause exists"]',
                        "fail_criteria": '["clause missing"]',
                        "sort_order": 0,
                    },
                ).scalar_one()

                conn.execute(
                    sa.text(
                        """
                        INSERT INTO checklist_item_sources (
                          checklist_item_id, source_type, authority, source_ref,
                          source_url, source_excerpt, interpretation_notes
                        )
                        VALUES (
                          :checklist_item_id, :source_type, :authority, :source_ref,
                          :source_url, :source_excerpt, :interpretation_notes
                        )
                        """
                    ),
                    {
                        "checklist_item_id": checklist_item_id,
                        "source_type": "LAW",
                        "authority": "EUR-Lex",
                        "source_ref": "Article 28",
                        "source_url": "https://example.com/legal",
                        "source_excerpt": "Processor shall process only on instructions.",
                        "interpretation_notes": "baseline mapping",
                    },
                )

                conn.execute(
                    sa.text(
                        """
                        INSERT INTO checklist_reviews (checklist_version_id, reviewer_id, decision, comment)
                        VALUES (:checklist_version_id, :reviewer_id, :decision, :comment)
                        """
                    ),
                    {
                        "checklist_version_id": checklist_version_id,
                        "reviewer_id": "reviewer-1",
                        "decision": "REVIEWED",
                        "comment": "Looks good",
                    },
                )

                conn.execute(
                    sa.text(
                        """
                        INSERT INTO checklist_approvals (checklist_version_id, approver_id, action, notes)
                        VALUES (:checklist_version_id, :approver_id, :action, :notes)
                        """
                    ),
                    {
                        "checklist_version_id": checklist_version_id,
                        "approver_id": "owner-1",
                        "action": "APPROVED_AND_PROMOTED",
                        "notes": "approved",
                    },
                )

                conn.execute(
                    sa.text(
                        """
                        INSERT INTO registry_audit_events (
                          actor_type, actor_id, event_name, resource_type, resource_id, trace_id, details
                        )
                        VALUES (
                          :actor_type, :actor_id, :event_name, :resource_type, :resource_id, :trace_id, :details::jsonb
                        )
                        """
                    ),
                    {
                        "actor_type": "user",
                        "actor_id": "owner-1",
                        "event_name": "registry.approve",
                        "resource_type": "checklist_versions",
                        "resource_id": "checklist_20260217_190000",
                        "trace_id": "trace-123",
                        "details": '{"status":"ACTIVE"}',
                    },
                )

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

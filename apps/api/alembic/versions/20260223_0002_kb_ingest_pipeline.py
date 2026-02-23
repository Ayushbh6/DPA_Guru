"""KB ingestion pipeline tables for regulatory corpus chunk processing.

Revision ID: 20260223_0002
Revises: 20260217_0001
Create Date: 2026-02-23
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "20260223_0002"
down_revision = "20260222_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    op.create_table(
        "kb_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("authority", sa.Text(), nullable=False),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("local_txt_path", sa.Text(), nullable=False),
        sa.Column("local_md_path", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("source_id", name="kb_sources_source_id_idx"),
    )

    op.create_table(
        "kb_ingest_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("kb_manifest_sha256", sa.Text(), nullable=False),
        sa.Column("chunk_size", sa.Integer(), nullable=False),
        sa.Column("chunk_overlap", sa.Integer(), nullable=False),
        sa.Column("full_doc_threshold", sa.Integer(), nullable=False),
        sa.Column("llm_model", sa.Text(), nullable=False),
        sa.Column("embedding_model", sa.Text(), nullable=False),
        sa.Column("llm_concurrency", sa.Integer(), nullable=False),
        sa.Column("embed_concurrency", sa.Integer(), nullable=False),
        sa.Column("upsert_concurrency", sa.Integer(), nullable=False),
        sa.Column("request_retries", sa.Integer(), nullable=False),
        sa.Column("total_chunks", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("completed_chunks", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("failed_chunks", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("error_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    op.create_table(
        "kb_ingest_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("kb_ingest_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("raw_text_sha256", sa.Text(), nullable=False),
        sa.Column("chunk_token_count", sa.Integer(), nullable=False),
        sa.Column("doc_token_count", sa.Integer(), nullable=False),
        sa.Column("context_mode", sa.Text(), nullable=False),
        sa.Column("context_window_start", sa.Integer(), nullable=False),
        sa.Column("context_window_end", sa.Integer(), nullable=False),
        sa.Column("context_text", sa.Text(), nullable=False),
        sa.Column("llm_status", sa.Text(), nullable=False, server_default=sa.text("'PENDING'")),
        sa.Column("llm_retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("llm_started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("llm_completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("llm_error", sa.Text(), nullable=True),
        sa.Column("structured_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("structured_text", sa.Text(), nullable=True),
        sa.Column("embed_status", sa.Text(), nullable=False, server_default=sa.text("'PENDING'")),
        sa.Column("embed_retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("embed_started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("embed_completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("embed_error", sa.Text(), nullable=True),
        sa.Column("embedding_dim", sa.Integer(), nullable=True),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("upsert_status", sa.Text(), nullable=False, server_default=sa.text("'PENDING'")),
        sa.Column("upsert_started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("upsert_completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("upsert_error", sa.Text(), nullable=True),
        sa.Column("final_status", sa.Text(), nullable=False, server_default=sa.text("'PENDING'")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("run_id", "source_id", "chunk_index", name="kb_ingest_tasks_run_source_chunk_uidx"),
    )

    op.create_table(
        "kb_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("source_title", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("chunk_token_count", sa.Integer(), nullable=False),
        sa.Column("doc_token_count", sa.Integer(), nullable=False),
        sa.Column("context_mode", sa.Text(), nullable=False),
        sa.Column("context_window_start", sa.Integer(), nullable=False),
        sa.Column("context_window_end", sa.Integer(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("structured_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("structured_text", sa.Text(), nullable=False),
        sa.Column("combined_text", sa.Text(), nullable=False),
        sa.Column("raw_text_sha256", sa.Text(), nullable=False),
        sa.Column("llm_model", sa.Text(), nullable=False),
        sa.Column("embedding_model", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("source_id", "chunk_index", name="kb_chunks_source_chunk_uidx"),
    )

    op.create_index("kb_ingest_runs_status_created_idx", "kb_ingest_runs", ["status", "created_at"])
    op.create_index("kb_ingest_tasks_run_final_idx", "kb_ingest_tasks", ["run_id", "final_status"])
    op.create_index("kb_ingest_tasks_run_llm_idx", "kb_ingest_tasks", ["run_id", "llm_status"])
    op.create_index("kb_ingest_tasks_run_embed_idx", "kb_ingest_tasks", ["run_id", "embed_status"])
    op.create_index("kb_ingest_tasks_run_upsert_idx", "kb_ingest_tasks", ["run_id", "upsert_status"])
    op.create_index("kb_ingest_tasks_source_chunk_idx", "kb_ingest_tasks", ["source_id", "chunk_index"])
    op.create_index("kb_chunks_source_idx", "kb_chunks", ["source_id", "chunk_index"])


def downgrade() -> None:
    op.drop_index("kb_chunks_source_idx", table_name="kb_chunks")
    op.drop_index("kb_ingest_tasks_source_chunk_idx", table_name="kb_ingest_tasks")
    op.drop_index("kb_ingest_tasks_run_upsert_idx", table_name="kb_ingest_tasks")
    op.drop_index("kb_ingest_tasks_run_embed_idx", table_name="kb_ingest_tasks")
    op.drop_index("kb_ingest_tasks_run_llm_idx", table_name="kb_ingest_tasks")
    op.drop_index("kb_ingest_tasks_run_final_idx", table_name="kb_ingest_tasks")
    op.drop_index("kb_ingest_runs_status_created_idx", table_name="kb_ingest_runs")
    op.drop_table("kb_chunks")
    op.drop_table("kb_ingest_tasks")
    op.drop_table("kb_ingest_runs")
    op.drop_table("kb_sources")

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from typing import Any

import psycopg
from psycopg.rows import dict_row

from kb_pipeline.config import PipelineConfig
from kb_pipeline.embed_client import combined_text_for_embedding
from kb_pipeline.models import PlanningResult, RunQueueSeed, TaskPayload


class KbRepository:
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url.replace("postgresql+psycopg://", "postgresql://")

    def _conn(self) -> psycopg.Connection[Any]:
        return psycopg.connect(self._database_url, row_factory=dict_row)

    def assert_schema_ready(self) -> None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT to_regclass('public.kb_ingest_runs') AS reg"
            ).fetchone()
            if not row or row["reg"] is None:
                raise RuntimeError(
                    "kb_* tables are missing. Run `make db-upgrade` to apply the kb pipeline migration."
                )

    def create_run_from_plan(self, plan: PlanningResult, config: PipelineConfig) -> str:
        run_id = str(uuid.uuid4())
        with self._conn() as conn:
            with conn.transaction():
                conn.execute(
                    """
                    INSERT INTO kb_ingest_runs (
                      id, status, kb_manifest_sha256, chunk_size, chunk_overlap, full_doc_threshold,
                      llm_model, embedding_model, llm_concurrency, embed_concurrency, upsert_concurrency,
                      request_retries, total_chunks
                    ) VALUES (
                      %(id)s, 'PENDING', %(manifest_sha)s, %(chunk_size)s, %(chunk_overlap)s, %(full_doc_threshold)s,
                      %(llm_model)s, %(embedding_model)s, %(llm_concurrency)s, %(embed_concurrency)s, %(upsert_concurrency)s,
                      %(request_retries)s, %(total_chunks)s
                    )
                    """,
                    {
                        "id": run_id,
                        "manifest_sha": plan.manifest_sha256,
                        "chunk_size": config.chunk_size,
                        "chunk_overlap": config.chunk_overlap,
                        "full_doc_threshold": config.full_doc_threshold_tokens,
                        "llm_model": config.openrouter_model,
                        "embedding_model": config.openai_embedding_model,
                        "llm_concurrency": config.llm_concurrency,
                        "embed_concurrency": config.embed_concurrency,
                        "upsert_concurrency": config.upsert_concurrency,
                        "request_retries": config.request_retries,
                        "total_chunks": len(plan.tasks),
                    },
                )
                for src in plan.sources:
                    conn.execute(
                        """
                        INSERT INTO kb_sources (
                          source_id, title, authority, source_kind, source_url, local_txt_path, local_md_path,
                          content_sha256, char_count, token_count, active
                        ) VALUES (
                          %(source_id)s, %(title)s, %(authority)s, %(source_kind)s, %(source_url)s, %(local_txt_path)s, %(local_md_path)s,
                          %(content_sha256)s, %(char_count)s, %(token_count)s, true
                        )
                        ON CONFLICT (source_id) DO UPDATE SET
                          title = EXCLUDED.title,
                          authority = EXCLUDED.authority,
                          source_kind = EXCLUDED.source_kind,
                          source_url = EXCLUDED.source_url,
                          local_txt_path = EXCLUDED.local_txt_path,
                          local_md_path = EXCLUDED.local_md_path,
                          content_sha256 = EXCLUDED.content_sha256,
                          char_count = EXCLUDED.char_count,
                          token_count = EXCLUDED.token_count,
                          active = true,
                          updated_at = now()
                        """,
                        asdict(src),
                    )
                for task in plan.tasks:
                    conn.execute(
                        """
                        INSERT INTO kb_ingest_tasks (
                          id, run_id, source_id, chunk_index, chunk_count, raw_text, raw_text_sha256,
                          chunk_token_count, doc_token_count, context_mode, context_window_start, context_window_end,
                          context_text, llm_status, embed_status, upsert_status, final_status
                        ) VALUES (
                          %(id)s, %(run_id)s, %(source_id)s, %(chunk_index)s, %(chunk_count)s, %(raw_text)s, %(raw_text_sha256)s,
                          %(chunk_token_count)s, %(doc_token_count)s, %(context_mode)s, %(context_window_start)s, %(context_window_end)s,
                          %(context_text)s, 'PENDING', 'PENDING', 'PENDING', 'PENDING'
                        )
                        """,
                        {
                            "id": str(uuid.uuid4()),
                            "run_id": run_id,
                            **asdict(task),
                        },
                    )
        return run_id

    def mark_run_started(self, run_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE kb_ingest_runs
                SET status = 'RUNNING', started_at = COALESCE(started_at, now())
                WHERE id = %(run_id)s
                """,
                {"run_id": run_id},
            )
            conn.commit()

    def cancel_run(self, run_id: str, reason: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE kb_ingest_runs
                SET status = 'CANCELLED', completed_at = now(), error_summary = jsonb_build_object('reason', %(reason)s)
                WHERE id = %(run_id)s
                """,
                {"run_id": run_id, "reason": reason},
            )
            conn.commit()

    def queue_seed(self, run_id: str, *, failed_only: bool = False) -> RunQueueSeed:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, final_status, llm_status, embed_status, upsert_status
                FROM kb_ingest_tasks
                WHERE run_id = %(run_id)s
                ORDER BY source_id, chunk_index
                """,
                {"run_id": run_id},
            ).fetchall()
        llm_ids: list[str] = []
        embed_ids: list[str] = []
        upsert_ids: list[str] = []
        for row in rows:
            if row["final_status"] == "COMPLETED":
                continue
            llm_status = row["llm_status"]
            embed_status = row["embed_status"]
            upsert_status = row["upsert_status"]

            if llm_status != "SUCCEEDED":
                if failed_only and llm_status != "FAILED":
                    continue
                llm_ids.append(str(row["id"]))
                continue
            if embed_status != "SUCCEEDED":
                if failed_only and embed_status != "FAILED":
                    continue
                embed_ids.append(str(row["id"]))
                continue
            if upsert_status != "SUCCEEDED":
                if failed_only and upsert_status != "FAILED":
                    continue
                upsert_ids.append(str(row["id"]))
        return RunQueueSeed(llm_task_ids=llm_ids, embed_task_ids=embed_ids, upsert_task_ids=upsert_ids)

    def load_task_payload(self, task_id: str) -> TaskPayload:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT
                  t.id::text AS task_id,
                  t.run_id::text AS run_id,
                  t.source_id,
                  s.title AS source_title,
                  s.source_url,
                  t.chunk_index,
                  t.chunk_count,
                  t.raw_text,
                  t.raw_text_sha256,
                  t.chunk_token_count,
                  t.doc_token_count,
                  t.context_mode,
                  t.context_window_start,
                  t.context_window_end,
                  t.context_text,
                  t.structured_json,
                  t.structured_text,
                  CASE WHEN t.embedding IS NULL THEN NULL ELSE t.embedding::text END AS embedding_text
                FROM kb_ingest_tasks t
                JOIN kb_sources s ON s.source_id = t.source_id
                WHERE t.id = %(task_id)s
                """,
                {"task_id": task_id},
            ).fetchone()
        if not row:
            raise KeyError(f"Task not found: {task_id}")
        embedding = self._parse_vector_text(row.get("embedding_text")) if row.get("embedding_text") else None
        structured_json = row.get("structured_json")
        if isinstance(structured_json, str):
            structured_json = json.loads(structured_json)
        return TaskPayload(
            task_id=row["task_id"],
            run_id=row["run_id"],
            source_id=row["source_id"],
            source_title=row["source_title"],
            source_url=row["source_url"],
            chunk_index=row["chunk_index"],
            chunk_count=row["chunk_count"],
            raw_text=row["raw_text"],
            raw_text_sha256=row["raw_text_sha256"],
            chunk_token_count=row["chunk_token_count"],
            doc_token_count=row["doc_token_count"],
            context_mode=row["context_mode"],
            context_window_start=row["context_window_start"],
            context_window_end=row["context_window_end"],
            context_text=row["context_text"],
            structured_json=structured_json,
            structured_text=row.get("structured_text"),
            embedding=embedding,
        )

    def mark_llm_running(self, task_id: str) -> None:
        self._mark_stage_running(task_id, stage="llm")

    def mark_embed_running(self, task_id: str) -> None:
        self._mark_stage_running(task_id, stage="embed")

    def mark_upsert_running(self, task_id: str) -> None:
        self._mark_stage_running(task_id, stage="upsert")

    def _mark_stage_running(self, task_id: str, *, stage: str) -> None:
        with self._conn() as conn:
            conn.execute(
                f"""
                UPDATE kb_ingest_tasks
                SET {stage}_status = 'RUNNING',
                    {stage}_started_at = now(),
                    {stage}_error = NULL,
                    updated_at = now()
                WHERE id = %(task_id)s
                """,
                {"task_id": task_id},
            )
            conn.commit()

    def save_llm_success(self, task_id: str, *, structured_json: dict[str, Any], structured_text: str, attempts_used: int) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE kb_ingest_tasks
                SET llm_status = 'SUCCEEDED',
                    llm_retry_count = %(retry_count)s,
                    llm_completed_at = now(),
                    structured_json = %(structured_json)s::jsonb,
                    structured_text = %(structured_text)s,
                    embed_status = CASE WHEN embed_status = 'SUCCEEDED' THEN embed_status ELSE 'PENDING' END,
                    upsert_status = CASE WHEN upsert_status = 'SUCCEEDED' THEN upsert_status ELSE 'PENDING' END,
                    final_status = CASE WHEN upsert_status = 'SUCCEEDED' THEN 'COMPLETED' ELSE 'PENDING' END,
                    updated_at = now()
                WHERE id = %(task_id)s
                """,
                {
                    "task_id": task_id,
                    "retry_count": max(0, attempts_used - 1),
                    "structured_json": json.dumps(structured_json, ensure_ascii=False),
                    "structured_text": structured_text,
                },
            )
            conn.commit()

    def save_llm_failure(self, task_id: str, *, error: str, attempts_used: int) -> None:
        self._save_stage_failure(task_id, stage="llm", error=error, attempts_used=attempts_used)

    def save_embed_success(self, task_id: str, *, embedding: list[float], attempts_used: int) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE kb_ingest_tasks
                SET embed_status = 'SUCCEEDED',
                    embed_retry_count = %(retry_count)s,
                    embed_completed_at = now(),
                    embedding_dim = %(embedding_dim)s,
                    embedding = %(embedding)s::vector,
                    upsert_status = CASE WHEN upsert_status = 'SUCCEEDED' THEN upsert_status ELSE 'PENDING' END,
                    final_status = CASE WHEN upsert_status = 'SUCCEEDED' THEN 'COMPLETED' ELSE 'PENDING' END,
                    updated_at = now()
                WHERE id = %(task_id)s
                """,
                {
                    "task_id": task_id,
                    "retry_count": max(0, attempts_used - 1),
                    "embedding_dim": len(embedding),
                    "embedding": self._vector_literal(embedding),
                },
            )
            conn.commit()

    def save_embed_failure(self, task_id: str, *, error: str, attempts_used: int) -> None:
        self._save_stage_failure(task_id, stage="embed", error=error, attempts_used=attempts_used)

    def save_upsert_success(self, task_id: str, *, llm_model: str, embedding_model: str) -> None:
        task = self.load_task_payload(task_id)
        if task.structured_json is None or task.embedding is None:
            raise ValueError("Task missing structured_json or embedding for upsert")
        combined_text = combined_text_for_embedding(task)
        with self._conn() as conn:
            with conn.transaction():
                conn.execute(
                    """
                    INSERT INTO kb_chunks (
                      source_id, source_title, source_url, chunk_index, chunk_count, chunk_token_count, doc_token_count,
                      context_mode, context_window_start, context_window_end, raw_text, structured_json, structured_text,
                      combined_text, raw_text_sha256, llm_model, embedding_model, embedding
                    ) VALUES (
                      %(source_id)s, %(source_title)s, %(source_url)s, %(chunk_index)s, %(chunk_count)s, %(chunk_token_count)s, %(doc_token_count)s,
                      %(context_mode)s, %(context_window_start)s, %(context_window_end)s, %(raw_text)s, %(structured_json)s::jsonb, %(structured_text)s,
                      %(combined_text)s, %(raw_text_sha256)s, %(llm_model)s, %(embedding_model)s, %(embedding)s::vector
                    )
                    ON CONFLICT (source_id, chunk_index) DO UPDATE SET
                      source_title = EXCLUDED.source_title,
                      source_url = EXCLUDED.source_url,
                      chunk_count = EXCLUDED.chunk_count,
                      chunk_token_count = EXCLUDED.chunk_token_count,
                      doc_token_count = EXCLUDED.doc_token_count,
                      context_mode = EXCLUDED.context_mode,
                      context_window_start = EXCLUDED.context_window_start,
                      context_window_end = EXCLUDED.context_window_end,
                      raw_text = EXCLUDED.raw_text,
                      structured_json = EXCLUDED.structured_json,
                      structured_text = EXCLUDED.structured_text,
                      combined_text = EXCLUDED.combined_text,
                      raw_text_sha256 = EXCLUDED.raw_text_sha256,
                      llm_model = EXCLUDED.llm_model,
                      embedding_model = EXCLUDED.embedding_model,
                      embedding = EXCLUDED.embedding,
                      updated_at = now()
                    """,
                    {
                        "source_id": task.source_id,
                        "source_title": task.source_title,
                        "source_url": task.source_url,
                        "chunk_index": task.chunk_index,
                        "chunk_count": task.chunk_count,
                        "chunk_token_count": task.chunk_token_count,
                        "doc_token_count": task.doc_token_count,
                        "context_mode": task.context_mode,
                        "context_window_start": task.context_window_start,
                        "context_window_end": task.context_window_end,
                        "raw_text": task.raw_text,
                        "structured_json": json.dumps(task.structured_json, ensure_ascii=False),
                        "structured_text": task.structured_text or json.dumps(task.structured_json, ensure_ascii=False),
                        "combined_text": combined_text,
                        "raw_text_sha256": task.raw_text_sha256,
                        "llm_model": llm_model,
                        "embedding_model": embedding_model,
                        "embedding": self._vector_literal(task.embedding),
                    },
                )
                conn.execute(
                    """
                    UPDATE kb_ingest_tasks
                    SET upsert_status = 'SUCCEEDED',
                        upsert_completed_at = now(),
                        final_status = 'COMPLETED',
                        updated_at = now()
                    WHERE id = %(task_id)s
                    """,
                    {"task_id": task_id},
                )
            conn.commit()

    def save_upsert_failure(self, task_id: str, *, error: str) -> None:
        self._save_stage_failure(task_id, stage="upsert", error=error, attempts_used=1)

    def _save_stage_failure(self, task_id: str, *, stage: str, error: str, attempts_used: int) -> None:
        retry_col = f"{stage}_retry_count"
        status_col = f"{stage}_status"
        error_col = f"{stage}_error"
        completed_col = f"{stage}_completed_at"
        with self._conn() as conn:
            conn.execute(
                f"""
                UPDATE kb_ingest_tasks
                SET {status_col} = 'FAILED',
                    {retry_col} = %(retry_count)s,
                    {error_col} = %(error)s,
                    {completed_col} = now(),
                    final_status = CASE WHEN %(stage)s = 'upsert' OR %(stage)s = 'embed' OR %(stage)s = 'llm' THEN 'FAILED' ELSE final_status END,
                    updated_at = now()
                WHERE id = %(task_id)s
                """,
                {
                    "task_id": task_id,
                    "retry_count": max(0, attempts_used - 1),
                    "error": error[:2000],
                    "stage": stage,
                },
            )
            conn.commit()

    def finalize_run(self, run_id: str) -> dict[str, Any]:
        with self._conn() as conn:
            counts = conn.execute(
                """
                SELECT
                  COUNT(*) AS total,
                  COUNT(*) FILTER (WHERE final_status = 'COMPLETED') AS completed,
                  COUNT(*) FILTER (WHERE final_status = 'FAILED') AS failed,
                  COUNT(*) FILTER (WHERE final_status = 'PENDING') AS pending,
                  COUNT(*) FILTER (WHERE llm_status = 'FAILED') AS llm_failed,
                  COUNT(*) FILTER (WHERE embed_status = 'FAILED') AS embed_failed,
                  COUNT(*) FILTER (WHERE upsert_status = 'FAILED') AS upsert_failed
                FROM kb_ingest_tasks
                WHERE run_id = %(run_id)s
                """,
                {"run_id": run_id},
            ).fetchone()
            if not counts:
                raise KeyError(f"Run not found: {run_id}")
            total = counts["total"]
            completed = counts["completed"]
            failed = counts["failed"]
            if completed == total and total > 0:
                status = "COMPLETED"
            elif completed > 0 and failed > 0:
                status = "PARTIAL_FAILURE"
            elif failed == total and total > 0:
                status = "FAILED"
            elif completed > 0 and counts["pending"] > 0:
                status = "PARTIAL_FAILURE"
            else:
                status = "FAILED" if failed > 0 else "RUNNING"
            error_summary = {
                "llm_failed": counts["llm_failed"],
                "embed_failed": counts["embed_failed"],
                "upsert_failed": counts["upsert_failed"],
            }
            conn.execute(
                """
                UPDATE kb_ingest_runs
                SET status = %(status)s,
                    completed_chunks = %(completed)s,
                    failed_chunks = %(failed)s,
                    completed_at = now(),
                    error_summary = %(error_summary)s::jsonb
                WHERE id = %(run_id)s
                """,
                {
                    "run_id": run_id,
                    "status": status,
                    "completed": completed,
                    "failed": failed,
                    "error_summary": json.dumps(error_summary),
                },
            )
            conn.commit()
        return self.status(run_id)

    def status(self, run_id: str) -> dict[str, Any]:
        with self._conn() as conn:
            run_row = conn.execute(
                "SELECT * FROM kb_ingest_runs WHERE id = %(run_id)s",
                {"run_id": run_id},
            ).fetchone()
            if not run_row:
                raise KeyError(f"Run not found: {run_id}")
            task_counts = conn.execute(
                """
                SELECT
                  COUNT(*) AS total,
                  COUNT(*) FILTER (WHERE final_status = 'COMPLETED') AS completed,
                  COUNT(*) FILTER (WHERE final_status = 'FAILED') AS failed,
                  COUNT(*) FILTER (WHERE llm_status = 'RUNNING') AS llm_running,
                  COUNT(*) FILTER (WHERE llm_status = 'PENDING') AS llm_pending,
                  COUNT(*) FILTER (WHERE embed_status = 'RUNNING') AS embed_running,
                  COUNT(*) FILTER (WHERE embed_status = 'PENDING' AND llm_status = 'SUCCEEDED') AS embed_pending_ready,
                  COUNT(*) FILTER (WHERE upsert_status = 'RUNNING') AS upsert_running,
                  COUNT(*) FILTER (WHERE upsert_status = 'PENDING' AND embed_status = 'SUCCEEDED') AS upsert_pending_ready
                FROM kb_ingest_tasks
                WHERE run_id = %(run_id)s
                """,
                {"run_id": run_id},
            ).fetchone()
            failures = conn.execute(
                """
                SELECT source_id, chunk_index, llm_error, embed_error, upsert_error
                FROM kb_ingest_tasks
                WHERE run_id = %(run_id)s
                  AND final_status = 'FAILED'
                ORDER BY source_id, chunk_index
                LIMIT 20
                """,
                {"run_id": run_id},
            ).fetchall()
        return {
            "run": {k: (str(v) if k == "id" else v) for k, v in dict(run_row).items()},
            "task_counts": dict(task_counts) if task_counts else {},
            "sample_failures": [dict(row) for row in failures],
        }

    def progress_counts_by_source(self, run_id: str) -> dict[str, dict[str, int]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT
                  source_id,
                  COUNT(*) AS total_chunks,
                  COUNT(*) FILTER (WHERE llm_status = 'RUNNING') AS llm_running,
                  COUNT(*) FILTER (WHERE llm_status = 'SUCCEEDED') AS llm_succeeded,
                  COUNT(*) FILTER (WHERE llm_status = 'FAILED') AS llm_failed,
                  COUNT(*) FILTER (WHERE embed_status = 'RUNNING') AS embed_running,
                  COUNT(*) FILTER (WHERE embed_status = 'SUCCEEDED') AS embed_succeeded,
                  COUNT(*) FILTER (WHERE embed_status = 'FAILED') AS embed_failed,
                  COUNT(*) FILTER (WHERE upsert_status = 'RUNNING') AS upsert_running,
                  COUNT(*) FILTER (WHERE upsert_status = 'SUCCEEDED') AS upsert_succeeded,
                  COUNT(*) FILTER (WHERE upsert_status = 'FAILED') AS upsert_failed
                FROM kb_ingest_tasks
                WHERE run_id = %(run_id)s
                GROUP BY source_id
                ORDER BY source_id
                """,
                {"run_id": run_id},
            ).fetchall()
        return {str(row["source_id"]): {k: int(v) for k, v in dict(row).items() if k != "source_id"} for row in rows}

    @staticmethod
    def _vector_literal(vec: list[float]) -> str:
        return "[" + ",".join(f"{float(v):.10f}" for v in vec) + "]"

    @staticmethod
    def _parse_vector_text(value: str | None) -> list[float] | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            return None
        if stripped[0] == "[" and stripped[-1] == "]":
            stripped = stripped[1:-1]
        if not stripped:
            return []
        return [float(part) for part in stripped.split(",")]

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from kb_pipeline.chunking import plan_from_kb
from kb_pipeline.config import PipelineConfig
from kb_pipeline.embed_client import OpenAIEmbeddingClient
from kb_pipeline.llm_client import OpenRouterClient
from kb_pipeline.models import PlanningResult, RunQueueSeed, TaskPayload
from kb_pipeline.repository import KbRepository


class KbPipelineOrchestrator:
    def __init__(self, config: PipelineConfig, repository: KbRepository) -> None:
        self.config = config
        self.repo = repository
        self.llm_client = OpenRouterClient(config)
        self.embed_client = OpenAIEmbeddingClient(config)

    def build_plan(
        self,
        *,
        kb_dir: str,
        source_ids: list[str] | None = None,
        max_chunks: int | None = None,
    ) -> PlanningResult:
        return plan_from_kb(
            kb_dir=Path(kb_dir),
            source_filter=set(source_ids) if source_ids else None,
            chunk_size=self.config.chunk_size,
            overlap=self.config.chunk_overlap,
            full_doc_threshold_tokens=self.config.full_doc_threshold_tokens,
            max_chunks=max_chunks,
        )

    async def run_new(self, *, kb_dir: str, source_ids: list[str] | None = None, max_chunks: int | None = None) -> dict[str, Any]:
        self.repo.assert_schema_ready()
        plan = self.build_plan(kb_dir=kb_dir, source_ids=source_ids, max_chunks=max_chunks)
        run_id = await asyncio.to_thread(self.repo.create_run_from_plan, plan, self.config)
        try:
            await self._execute_run(run_id, failed_only=False)
        except BaseException:
            await asyncio.to_thread(self.repo.cancel_run, run_id, "Interrupted during run execution")
            raise
        status = await asyncio.to_thread(self.repo.finalize_run, run_id)
        return {"run_id": run_id, "plan": plan.summary, "status": status}

    async def resume(self, run_id: str, *, failed_only: bool = False) -> dict[str, Any]:
        self.repo.assert_schema_ready()
        await self._execute_run(run_id, failed_only=failed_only)
        return await asyncio.to_thread(self.repo.finalize_run, run_id)

    async def _execute_run(self, run_id: str, *, failed_only: bool) -> None:
        await asyncio.to_thread(self.repo.mark_run_started, run_id)
        seed = await asyncio.to_thread(self.repo.queue_seed, run_id, failed_only=failed_only)
        progress = await asyncio.to_thread(self.repo.progress_counts_by_source, run_id)
        progress_lock = asyncio.Lock()
        self._log_progress_init(run_id, progress)
        progress_stop = asyncio.Event()
        progress_monitor = asyncio.create_task(self._progress_monitor(run_id, progress, progress_lock, progress_stop))

        llm_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=self.config.queue_maxsize)
        embed_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=self.config.queue_maxsize)
        upsert_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=max(self.config.queue_maxsize, 256))

        llm_workers = [
            asyncio.create_task(
                self._llm_worker(
                    run_id,
                    llm_queue,
                    embed_queue,
                    worker_idx=i,
                    progress=progress,
                    progress_lock=progress_lock,
                )
            )
            for i in range(max(1, self.config.llm_concurrency))
        ]
        embed_workers = [
            asyncio.create_task(
                self._embed_worker(
                    run_id,
                    embed_queue,
                    upsert_queue,
                    worker_idx=i,
                    progress=progress,
                    progress_lock=progress_lock,
                )
            )
            for i in range(max(1, self.config.embed_concurrency))
        ]
        upsert_workers = [
            asyncio.create_task(
                self._upsert_worker(
                    run_id,
                    upsert_queue,
                    worker_idx=i,
                    progress=progress,
                    progress_lock=progress_lock,
                )
            )
            for i in range(max(1, self.config.upsert_concurrency))
        ]

        # Start consumers before seeding bounded queues; otherwise large runs can block
        # during initial queue fill (e.g. > queue_maxsize tasks) and appear "hung".
        for task_id in seed.llm_task_ids:
            await llm_queue.put(task_id)
        for task_id in seed.embed_task_ids:
            await embed_queue.put(task_id)
        for task_id in seed.upsert_task_ids:
            await upsert_queue.put(task_id)

        try:
            await llm_queue.join()
            await embed_queue.join()
            await upsert_queue.join()
        finally:
            progress_stop.set()
            for q, workers in ((llm_queue, llm_workers), (embed_queue, embed_workers), (upsert_queue, upsert_workers)):
                for _ in workers:
                    await q.put("__STOP__")
            await asyncio.gather(*llm_workers, *embed_workers, *upsert_workers, progress_monitor, return_exceptions=True)

    async def _llm_worker(
        self,
        run_id: str,
        llm_queue: asyncio.Queue[str],
        embed_queue: asyncio.Queue[str],
        *,
        worker_idx: int,
        progress: dict[str, dict[str, int]],
        progress_lock: asyncio.Lock,
    ) -> None:
        while True:
            task_id = await llm_queue.get()
            if task_id == "__STOP__":
                llm_queue.task_done()
                return
            started = time.perf_counter()
            try:
                await asyncio.to_thread(self.repo.mark_llm_running, task_id)
                task = await asyncio.to_thread(self.repo.load_task_payload, task_id)
                await self._log_progress_stage_start(progress, progress_lock, task, stage="llm")
                result = await self.llm_client.extract(task)
                await asyncio.to_thread(
                    self.repo.save_llm_success,
                    task_id,
                    structured_json=result.structured_json,
                    structured_text=result.structured_text,
                    attempts_used=result.attempts_used,
                )
                await embed_queue.put(task_id)
                self._log_event(
                    run_id,
                    task,
                    stage="llm",
                    status="SUCCEEDED",
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    retry_count=max(0, result.attempts_used - 1),
                    worker_idx=worker_idx,
                )
                await self._log_progress_update(progress, progress_lock, task, stage="llm", status="SUCCEEDED")
            except Exception as exc:
                task_for_log = None
                try:
                    task_for_log = await asyncio.to_thread(self.repo.load_task_payload, task_id)
                except Exception:
                    pass
                await asyncio.to_thread(self.repo.save_llm_failure, task_id, error=str(exc), attempts_used=1)
                self._log_event(
                    run_id,
                    task_for_log,
                    stage="llm",
                    status="FAILED",
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    retry_count=0,
                    worker_idx=worker_idx,
                    error=str(exc),
                )
                if task_for_log is not None:
                    await self._log_progress_update(progress, progress_lock, task_for_log, stage="llm", status="FAILED")
            finally:
                llm_queue.task_done()

    async def _embed_worker(
        self,
        run_id: str,
        embed_queue: asyncio.Queue[str],
        upsert_queue: asyncio.Queue[str],
        *,
        worker_idx: int,
        progress: dict[str, dict[str, int]],
        progress_lock: asyncio.Lock,
    ) -> None:
        while True:
            task_id = await embed_queue.get()
            if task_id == "__STOP__":
                embed_queue.task_done()
                return
            started = time.perf_counter()
            try:
                await asyncio.to_thread(self.repo.mark_embed_running, task_id)
                task = await asyncio.to_thread(self.repo.load_task_payload, task_id)
                await self._log_progress_stage_start(progress, progress_lock, task, stage="embed")
                result = await self.embed_client.embed(task)
                await asyncio.to_thread(
                    self.repo.save_embed_success,
                    task_id,
                    embedding=result.embedding,
                    attempts_used=result.attempts_used,
                )
                await upsert_queue.put(task_id)
                self._log_event(
                    run_id,
                    task,
                    stage="embed",
                    status="SUCCEEDED",
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    retry_count=max(0, result.attempts_used - 1),
                    worker_idx=worker_idx,
                )
                await self._log_progress_update(progress, progress_lock, task, stage="embed", status="SUCCEEDED")
            except Exception as exc:
                task_for_log = None
                try:
                    task_for_log = await asyncio.to_thread(self.repo.load_task_payload, task_id)
                except Exception:
                    pass
                await asyncio.to_thread(self.repo.save_embed_failure, task_id, error=str(exc), attempts_used=1)
                self._log_event(
                    run_id,
                    task_for_log,
                    stage="embed",
                    status="FAILED",
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    retry_count=0,
                    worker_idx=worker_idx,
                    error=str(exc),
                )
                if task_for_log is not None:
                    await self._log_progress_update(progress, progress_lock, task_for_log, stage="embed", status="FAILED")
            finally:
                embed_queue.task_done()

    async def _upsert_worker(
        self,
        run_id: str,
        upsert_queue: asyncio.Queue[str],
        *,
        worker_idx: int,
        progress: dict[str, dict[str, int]],
        progress_lock: asyncio.Lock,
    ) -> None:
        while True:
            task_id = await upsert_queue.get()
            if task_id == "__STOP__":
                upsert_queue.task_done()
                return
            started = time.perf_counter()
            try:
                await asyncio.to_thread(self.repo.mark_upsert_running, task_id)
                task = await asyncio.to_thread(self.repo.load_task_payload, task_id)
                await self._log_progress_stage_start(progress, progress_lock, task, stage="upsert")
                await asyncio.to_thread(
                    self.repo.save_upsert_success,
                    task_id,
                    llm_model=self.config.openrouter_model,
                    embedding_model=self.config.openai_embedding_model,
                )
                self._log_event(
                    run_id,
                    task,
                    stage="upsert",
                    status="SUCCEEDED",
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    retry_count=0,
                    worker_idx=worker_idx,
                )
                await self._log_progress_update(progress, progress_lock, task, stage="upsert", status="SUCCEEDED")
            except Exception as exc:
                task_for_log = None
                try:
                    task_for_log = await asyncio.to_thread(self.repo.load_task_payload, task_id)
                except Exception:
                    pass
                await asyncio.to_thread(self.repo.save_upsert_failure, task_id, error=str(exc))
                self._log_event(
                    run_id,
                    task_for_log,
                    stage="upsert",
                    status="FAILED",
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    retry_count=0,
                    worker_idx=worker_idx,
                    error=str(exc),
                )
                if task_for_log is not None:
                    await self._log_progress_update(progress, progress_lock, task_for_log, stage="upsert", status="FAILED")
            finally:
                upsert_queue.task_done()

    def _log_event(
        self,
        run_id: str,
        task: TaskPayload | None,
        *,
        stage: str,
        status: str,
        latency_ms: int,
        retry_count: int,
        worker_idx: int,
        error: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "event": "kb_pipeline.chunk_stage",
            "run_id": run_id,
            "stage": stage,
            "status": status,
            "latency_ms": latency_ms,
            "retry_count": retry_count,
            "worker_idx": worker_idx,
            "trace_id": f"{run_id}:{task.task_id if task else 'unknown'}:{stage}",
        }
        if task is not None:
            payload.update({"source_id": task.source_id, "chunk_index": task.chunk_index, "chunk_count": task.chunk_count})
        if error:
            payload["error"] = error[:500]
        print(json.dumps(payload, ensure_ascii=False), flush=True)

    def _log_progress_init(self, run_id: str, progress: Mapping[str, Mapping[str, int]]) -> None:
        if not progress:
            print(f"[progress][init] run={run_id} no tasks queued", flush=True)
            return
        total_chunks = sum(int(counters.get("total_chunks", 0)) for counters in progress.values())
        print(f"[progress][init] run={run_id} sources={len(progress)} total_chunks={total_chunks}", flush=True)

    async def _progress_monitor(
        self,
        run_id: str,
        progress: dict[str, dict[str, int]],
        progress_lock: asyncio.Lock,
        stop_event: asyncio.Event,
    ) -> None:
        interval = max(2, int(self.config.progress_heartbeat_seconds))
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
                break
            except asyncio.TimeoutError:
                pass
            async with progress_lock:
                active_rows: list[str] = []
                for source_id, counters in sorted(progress.items()):
                    total = int(counters.get("total_chunks", 0))
                    llm_running = int(counters.get("llm_running", 0))
                    embed_running = int(counters.get("embed_running", 0))
                    upsert_running = int(counters.get("upsert_running", 0))
                    llm_done = int(counters.get("llm_succeeded", 0)) + int(counters.get("llm_failed", 0))
                    embed_done = int(counters.get("embed_succeeded", 0)) + int(counters.get("embed_failed", 0))
                    upsert_done = int(counters.get("upsert_succeeded", 0)) + int(counters.get("upsert_failed", 0))
                    has_activity = any(
                        [
                            llm_running,
                            embed_running,
                            upsert_running,
                            llm_done,
                            embed_done,
                            upsert_done,
                        ]
                    )
                    is_complete = total > 0 and upsert_done >= total
                    if has_activity and not is_complete:
                        active_rows.append(
                            f"{source_id}: llm={llm_done}/{total} (running={llm_running}) "
                            f"embed={embed_done}/{total} (running={embed_running}) "
                            f"upsert={upsert_done}/{total} (running={upsert_running})"
                        )
                if active_rows:
                    print(f"[progress][heartbeat] run={run_id}", flush=True)
                    for row in active_rows:
                        print(f"[progress][heartbeat] {row}", flush=True)

    async def _log_progress_stage_start(
        self,
        progress: dict[str, dict[str, int]],
        progress_lock: asyncio.Lock,
        task: TaskPayload,
        *,
        stage: str,
    ) -> None:
        running_key = f"{stage}_running"
        async with progress_lock:
            source = progress.setdefault(
                task.source_id,
                {
                    "total_chunks": task.chunk_count,
                    "llm_running": 0,
                    "llm_succeeded": 0,
                    "llm_failed": 0,
                    "embed_running": 0,
                    "embed_succeeded": 0,
                    "embed_failed": 0,
                    "upsert_running": 0,
                    "upsert_succeeded": 0,
                    "upsert_failed": 0,
                },
            )
            source[running_key] = int(source.get(running_key, 0)) + 1
            print(
                f"[progress][{stage}-start] {task.source_id} chunk={task.chunk_index + 1}/{task.chunk_count}",
                flush=True,
            )

    async def _log_progress_update(
        self,
        progress: dict[str, dict[str, int]],
        progress_lock: asyncio.Lock,
        task: TaskPayload,
        *,
        stage: str,
        status: str,
    ) -> None:
        stage_key_prefix = f"{stage}_{'succeeded' if status == 'SUCCEEDED' else 'failed'}"
        running_key = f"{stage}_running"
        async with progress_lock:
            source = progress.setdefault(
                task.source_id,
                {
                    "total_chunks": task.chunk_count,
                    "llm_running": 0,
                    "llm_succeeded": 0,
                    "llm_failed": 0,
                    "embed_running": 0,
                    "embed_succeeded": 0,
                    "embed_failed": 0,
                    "upsert_running": 0,
                    "upsert_succeeded": 0,
                    "upsert_failed": 0,
                },
            )
            source[running_key] = max(0, int(source.get(running_key, 0)) - 1)
            source[stage_key_prefix] = int(source.get(stage_key_prefix, 0)) + 1
            total = int(source.get("total_chunks", task.chunk_count))
            llm_running = int(source.get("llm_running", 0))
            llm_ok = int(source.get("llm_succeeded", 0))
            llm_fail = int(source.get("llm_failed", 0))
            embed_running = int(source.get("embed_running", 0))
            embed_ok = int(source.get("embed_succeeded", 0))
            embed_fail = int(source.get("embed_failed", 0))
            upsert_running = int(source.get("upsert_running", 0))
            upsert_ok = int(source.get("upsert_succeeded", 0))
            upsert_fail = int(source.get("upsert_failed", 0))
            print(
                f"[progress][{stage.lower()}] {task.source_id} "
                f"chunks={task.chunk_count} "
                f"llm={llm_ok + llm_fail}/{total} (ok={llm_ok}, fail={llm_fail}, running={llm_running}) "
                f"embed={embed_ok + embed_fail}/{total} (ok={embed_ok}, fail={embed_fail}, running={embed_running}) "
                f"upsert={upsert_ok + upsert_fail}/{total} (ok={upsert_ok}, fail={upsert_fail}, running={upsert_running})",
                flush=True,
            )
